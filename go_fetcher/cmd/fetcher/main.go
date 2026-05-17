package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"log/slog"
	"os"
	"time"

	"github.com/joho/godotenv"

	"go_fetcher/internal/config"
	"go_fetcher/internal/parsers/wildberries"
	"go_fetcher/internal/pipeline"
	"go_fetcher/internal/sender"
)

const (
	sourceWildberries = "wildberries"
	defaultLimit      = 100
)

func main() {
	logger := newLogger()

	if err := godotenv.Load(); err != nil {
		logger.Warn("no .env file found")
	}

	cfg, err := config.Load()
	if err != nil {
		logger.Error("failed to load config", slog.String("error", err.Error()))
		os.Exit(1)
	}

	if len(os.Args) < 3 {
		printUsageAndExit()
	}

	source := os.Args[1]
	command := os.Args[2]

	if source != "wb" {
		logger.Error("unsupported source", slog.String("source", source))
		os.Exit(1)
	}

	ctx, cancel := context.WithTimeout(context.Background(), cfg.Timeout)
	defer cancel()

	wbParser := wildberries.NewParser(
		wildberries.ParserConfig{
			Cookie:         cfg.WBCookie,
			Timeout:        cfg.Timeout,
			RequestDelay:   cfg.WBRequestDelay,
			MaxRetries:     cfg.WBMaxRetries,
			RetryBaseDelay: cfg.WBRetryBaseDelay,
		},
		logger,
	)

	djangoSender := sender.NewDjangoSender(
		cfg.DjangoURL,
		cfg.FetcherAPIKey,
	)

	importPipeline := pipeline.NewImportPipeline(
		djangoSender,
	)

	startedAt := time.Now()

	logger.Info(
		"fetcher command started",
		slog.String("source", source),
		slog.String("command", command),
	)

	switch command {
	case "product":
		runWBProductCommand(ctx, logger, wbParser, importPipeline)

	case "search":
		runWBSearchCommand(ctx, logger, wbParser, importPipeline)

	case "category":
		runWBCategoryCommand(ctx, logger, wbParser, importPipeline)

	default:
		logger.Error("unsupported wb command", slog.String("command", command))
		os.Exit(1)
	}

	logger.Info(
		"fetcher command finished",
		slog.String("source", source),
		slog.String("command", command),
		slog.Duration("duration", time.Since(startedAt)),
	)
}

func runWBProductCommand(
	ctx context.Context,
	logger *slog.Logger,
	wbParser *wildberries.Parser,
	importPipeline *pipeline.ImportPipeline,
) {
	productFlags := flag.NewFlagSet("wb product", flag.ExitOnError)

	if err := productFlags.Parse(os.Args[3:]); err != nil {
		logger.Error("failed to parse product flags", slog.String("error", err.Error()))
		os.Exit(1)
	}

	if productFlags.NArg() != 1 {
		logger.Error("invalid product command arguments")
		log.Fatal("usage: go run ./cmd/fetcher wb product <nmID>")
	}

	nmID := productFlags.Arg(0)

	logger.Info(
		"wb product command parsed",
		slog.String("nm_id", nmID),
	)

	products, err := wbParser.ParseProduct(ctx, nmID)
	if err != nil {
		logger.Error("failed to parse WB product", slog.String("error", err.Error()))
		os.Exit(1)
	}

	response, err := importPipeline.ImportProducts(
		ctx,
		sourceWildberries,
		products,
	)
	if err != nil {
		logger.Error("failed to import WB product", slog.String("error", err.Error()))
		os.Exit(1)
	}

	printImportResponse(response)
}

func runWBSearchCommand(
	ctx context.Context,
	logger *slog.Logger,
	wbParser *wildberries.Parser,
	importPipeline *pipeline.ImportPipeline,
) {
	searchFlags := flag.NewFlagSet("wb search", flag.ExitOnError)

	limit := searchFlags.Int("limit", defaultLimit, "maximum number of products to import")

	if err := searchFlags.Parse(os.Args[3:]); err != nil {
		logger.Error("failed to parse search flags", slog.String("error", err.Error()))
		os.Exit(1)
	}

	if searchFlags.NArg() != 1 {
		logger.Error("invalid search command arguments")
		log.Fatal(`usage: go run ./cmd/fetcher wb search --limit=100 "iphone"`)
	}

	query := searchFlags.Arg(0)

	logger.Info(
		"wb search command parsed",
		slog.String("query", query),
		slog.Int("limit", *limit),
	)

	products, err := wbParser.SearchProducts(ctx, query, *limit)
	if err != nil {
		logger.Error("failed to parse WB search products", slog.String("error", err.Error()))
		os.Exit(1)
	}

	response, err := importPipeline.ImportProducts(
		ctx,
		sourceWildberries,
		products,
	)
	if err != nil {
		logger.Error("failed to import WB search products", slog.String("error", err.Error()))
		os.Exit(1)
	}

	printImportResponse(response)
}

func runWBCategoryCommand(
	ctx context.Context,
	logger *slog.Logger,
	wbParser *wildberries.Parser,
	importPipeline *pipeline.ImportPipeline,
) {
	categoryFlags := flag.NewFlagSet("wb category", flag.ExitOnError)

	limit := categoryFlags.Int("limit", defaultLimit, "maximum number of products to import")

	if err := categoryFlags.Parse(os.Args[3:]); err != nil {
		logger.Error("failed to parse category flags", slog.String("error", err.Error()))
		os.Exit(1)
	}

	if categoryFlags.NArg() != 1 {
		logger.Error("invalid category command arguments")
		log.Fatal(`usage: go run ./cmd/fetcher wb category --limit=100 "кошельки и кредитницы"`)
	}

	categoryName := categoryFlags.Arg(0)

	logger.Info(
		"wb category command parsed",
		slog.String("category", categoryName),
		slog.Int("limit", *limit),
	)

	products, err := wbParser.CategoryProducts(ctx, categoryName, *limit)
	if err != nil {
		logger.Error("failed to parse WB category products", slog.String("error", err.Error()))
		os.Exit(1)
	}

	response, err := importPipeline.ImportProducts(
		ctx,
		sourceWildberries,
		products,
	)
	if err != nil {
		logger.Error("failed to import WB category products", slog.String("error", err.Error()))
		os.Exit(1)
	}

	printImportResponse(response)
}

func printImportResponse(response pipeline.ImportResponse) {
	fmt.Printf("Django import success: %t\n", response.Success)
	fmt.Printf("Django import status: %s\n", response.Status)
	fmt.Printf("Created: %d\n", response.Created)
	fmt.Printf("Updated: %d\n", response.Updated)
}

func printUsageAndExit() {
	fmt.Println("usage:")
	fmt.Println("  go run ./cmd/fetcher wb product <nmID>")
	fmt.Println(`  go run ./cmd/fetcher wb search --limit=100 "iphone"`)
	fmt.Println(`  go run ./cmd/fetcher wb category --limit=100 "кошельки и кредитницы"`)
	os.Exit(1)
}

func newLogger() *slog.Logger {
	handler := slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	})

	logger := slog.New(handler)
	slog.SetDefault(logger)

	return logger
}
