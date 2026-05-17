package main

import (
	"context"
	"flag"
	"fmt"
	"log"
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
	defaultTimeout    = 30 * time.Second
	defaultLimit      = 100
)

func main() {
	if err := godotenv.Load(); err != nil {
		log.Println("No .env file found")
	}

	cfg, err := config.Load()
	if err != nil {
		log.Fatal(err)
	}

	if len(os.Args) < 3 {
		printUsageAndExit()
	}

	source := os.Args[1]
	command := os.Args[2]

	if source != "wb" {
		log.Fatalf("unsupported source: %s", source)
	}

	ctx, cancel := context.WithTimeout(context.Background(), defaultTimeout)
	defer cancel()

	wbParser := wildberries.NewParser()

	djangoSender := sender.NewDjangoSender(
		cfg.DjangoURL,
		cfg.FetcherAPIKey,
	)

	importPipeline := pipeline.NewImportPipeline(
		djangoSender,
	)

	switch command {
	case "product":
		runWBProductCommand(ctx, wbParser, importPipeline)

	case "search":
		runWBSearchCommand(ctx, wbParser, importPipeline)

	case "category":
		runWBCategoryCommand(ctx, wbParser, importPipeline)

	default:
		log.Fatalf("unsupported wb command: %s", command)
	}
}

func runWBProductCommand(
	ctx context.Context,
	wbParser *wildberries.Parser,
	importPipeline *pipeline.ImportPipeline,
) {
	productFlags := flag.NewFlagSet("wb product", flag.ExitOnError)

	if err := productFlags.Parse(os.Args[3:]); err != nil {
		log.Fatal(err)
	}

	if productFlags.NArg() != 1 {
		log.Fatal("usage: go run ./cmd/fetcher wb product <nmID>")
	}

	nmID := productFlags.Arg(0)

	products, err := wbParser.ParseProduct(ctx, nmID)
	if err != nil {
		log.Fatal(err)
	}

	response, err := importPipeline.ImportProducts(
		ctx,
		sourceWildberries,
		products,
	)
	if err != nil {
		log.Fatal(err)
	}

	printImportResponse(response)
}

func runWBSearchCommand(
	ctx context.Context,
	wbParser *wildberries.Parser,
	importPipeline *pipeline.ImportPipeline,
) {
	searchFlags := flag.NewFlagSet("wb search", flag.ExitOnError)

	limit := searchFlags.Int("limit", defaultLimit, "maximum number of products to import")

	if err := searchFlags.Parse(os.Args[3:]); err != nil {
		log.Fatal(err)
	}

	if searchFlags.NArg() != 1 {
		log.Fatal(`usage: go run ./cmd/fetcher wb search "iphone" --limit=100`)
	}

	query := searchFlags.Arg(0)

	products, err := wbParser.SearchProducts(ctx, query, *limit)
	if err != nil {
		log.Fatal(err)
	}

	response, err := importPipeline.ImportProducts(
		ctx,
		sourceWildberries,
		products,
	)
	if err != nil {
		log.Fatal(err)
	}

	printImportResponse(response)
}

func runWBCategoryCommand(
	ctx context.Context,
	wbParser *wildberries.Parser,
	importPipeline *pipeline.ImportPipeline,
) {
	categoryFlags := flag.NewFlagSet("wb category", flag.ExitOnError)

	limit := categoryFlags.Int("limit", defaultLimit, "maximum number of products to import")

	if err := categoryFlags.Parse(os.Args[3:]); err != nil {
		log.Fatal(err)
	}

	if categoryFlags.NArg() != 1 {
		log.Fatal(`usage: go run ./cmd/fetcher wb category "https://www.wildberries.ru/catalog/..." --limit=100`)
	}

	categoryURL := categoryFlags.Arg(0)

	products, err := wbParser.CategoryProducts(ctx, categoryURL, *limit)
	if err != nil {
		log.Fatal(err)
	}

	response, err := importPipeline.ImportProducts(
		ctx,
		sourceWildberries,
		products,
	)
	if err != nil {
		log.Fatal(err)
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
	fmt.Println(`  go run ./cmd/fetcher wb search "iphone" --limit=100`)
	fmt.Println(`  go run ./cmd/fetcher wb category "https://www.wildberries.ru/catalog/..." --limit=100`)
	os.Exit(1)
}
