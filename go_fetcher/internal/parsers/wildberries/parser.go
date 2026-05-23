package wildberries

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"go_fetcher/internal/models"
)

const (
	defaultCurrency = "RUB"

	detailURL  = "https://www.wildberries.ru/__internal/card/cards/v4/detail"
	catalogURL = "https://www.wildberries.ru/__internal/search/exactmatch/ru/common/v18/search"

	defaultPageSize = 100
)

type Parser struct {
	client         *http.Client
	logger         *slog.Logger
	cookie         string
	requestDelay   time.Duration
	maxRetries     int
	retryBaseDelay time.Duration
}

type ParserConfig struct {
	Cookie         string
	Timeout        time.Duration
	RequestDelay   time.Duration
	MaxRetries     int
	RetryBaseDelay time.Duration
}

func NewParser(cfg ParserConfig, logger *slog.Logger) *Parser {
	if logger == nil {
		logger = slog.Default()
	}

	if cfg.Timeout <= 0 {
		cfg.Timeout = 15 * time.Second
	}

	if cfg.RequestDelay < 0 {
		cfg.RequestDelay = 0
	}

	if cfg.MaxRetries < 0 {
		cfg.MaxRetries = 0
	}

	if cfg.RetryBaseDelay <= 0 {
		cfg.RetryBaseDelay = 1 * time.Second
	}

	return &Parser{
		client: &http.Client{
			Timeout: cfg.Timeout,
		},
		logger:         logger,
		cookie:         cfg.Cookie,
		requestDelay:   cfg.RequestDelay,
		maxRetries:     cfg.MaxRetries,
		retryBaseDelay: cfg.RetryBaseDelay,
	}
}

func (p *Parser) ParseProduct(ctx context.Context, nmID string) ([]models.Product, error) {
	nmID = strings.TrimSpace(nmID)
	if nmID == "" {
		return nil, fmt.Errorf("nmID is empty")
	}

	requestURL := buildDetailURL(nmID)

	var response wbProductsResponse

	if err := p.doJSONRequest(ctx, requestURL, &response); err != nil {
		return nil, fmt.Errorf("parse WB product %s: %w", nmID, err)
	}

	products := normalizeWBProducts(response.Products)
	products = deduplicateProductsBySKU(products)

	p.logger.Info(
		"wildberries product parsed",
		slog.String("nm_id", nmID),
		slog.Int("products_found", len(products)),
	)

	return products, nil
}

func (p *Parser) SearchProducts(ctx context.Context, query string, limit int) ([]models.Product, error) {
	query = strings.TrimSpace(query)

	if query == "" {
		return nil, fmt.Errorf("search query is empty")
	}

	if limit <= 0 {
		return nil, fmt.Errorf("limit must be greater than zero")
	}

	p.logger.Info(
		"wildberries search import started",
		slog.String("query", query),
		slog.Int("limit", limit),
	)

	products, err := p.fetchCatalogProducts(
		ctx,
		"search",
		query,
		limit,
		func(page int) string {
			return buildSearchURL(query, page)
		},
	)
	if err != nil {
		return nil, fmt.Errorf("search WB products by query %q: %w", query, err)
	}

	p.logger.Info(
		"wildberries search import parsed",
		slog.String("query", query),
		slog.Int("products_found", len(products)),
	)

	return products, nil
}

func (p *Parser) CategoryProducts(ctx context.Context, categoryName string, limit int) ([]models.Product, error) {
	categoryName = strings.TrimSpace(categoryName)

	if categoryName == "" {
		return nil, fmt.Errorf("category name is empty")
	}

	if limit <= 0 {
		return nil, fmt.Errorf("limit must be greater than zero")
	}

	p.logger.Info(
		"wildberries category import started",
		slog.String("category", categoryName),
		slog.Int("limit", limit),
	)

	products, err := p.fetchCatalogProducts(
		ctx,
		"category",
		categoryName,
		limit,
		func(page int) string {
			return buildCategoryURL(categoryName, page)
		},
	)
	if err != nil {
		return nil, fmt.Errorf("parse WB category %q: %w", categoryName, err)
	}

	p.logger.Info(
		"wildberries category import parsed",
		slog.String("category", categoryName),
		slog.Int("products_found", len(products)),
	)

	return products, nil
}
