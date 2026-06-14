package ozon

import (
	"context"
	"fmt"
	"go_fetcher/internal/cookies"
	"go_fetcher/internal/models"
	"log/slog"
	"net/http"
	"strings"
	"time"
)

const (
	defaultCurrency = "RUB"

	ozonPageAPIURL = "https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2"
)

type Parser struct {
	client         *http.Client
	logger         *slog.Logger
	cookie         string
	cookieProvider cookies.Provider
	requestDelay   time.Duration
	maxRetries     int
	retryBaseDelay time.Duration
}

type ParserConfig struct {
	Cookie         string
	CookieProvider cookies.Provider
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
		cookieProvider: cfg.CookieProvider,
		requestDelay:   cfg.RequestDelay,
		maxRetries:     cfg.MaxRetries,
		retryBaseDelay: cfg.RetryBaseDelay,
	}
}

func (p *Parser) ParseProduct(ctx context.Context, productInput string) ([]models.Product, error) {
	productInput = strings.TrimSpace(productInput)
	if productInput == "" {
		return nil, fmt.Errorf("productInput is empty")
	}

	requestURL, productPath, err := buildProductRequestURL(productInput)
	if err != nil {
		return nil, err
	}

	productID := extractProductID(productPath)
	if productID == "" {
		return nil, fmt.Errorf("failed to extract product id from %q", productInput)
	}

	var response ozonPageResponse

	if err := p.doJSONRequest(ctx, requestURL, &response); err != nil {
		return nil, fmt.Errorf("parse Ozon product %s: %w", productID, err)
	}

	// debugOzonWidgetStates(response.WidgetStates)

	products := extractProductsFromWidgetStates(response.WidgetStates)
	products = deduplicateProductsBySKU(products)

	if len(products) == 0 {
		return nil, fmt.Errorf("no products extracted from Ozon widgetStates")
	}

	product := findProductBySKU(products, productID)
	if product == nil {
		product = &products[0]
	}

	p.logger.Info(
		"ozon product parsed",
		slog.String("product_id", productID),
		slog.String("sku", product.SKU),
		slog.String("title", product.Title),
		slog.Int("price_cents", product.PriceCents),
		slog.Int("available", product.Available),
	)

	return []models.Product{*product}, nil
}

func (p *Parser) SearchProducts(ctx context.Context, query string, limit int) ([]models.Product, error) {
	query = strings.TrimSpace(query)

	if query == "" {
		return nil, fmt.Errorf("search query is empty")
	}

	if limit <= 0 {
		return nil, fmt.Errorf("limit must be greater than zero")
	}

	return p.fetchCatalogProducts(ctx, CatalogRequest{
		Mode:  "search",
		Input: query,
		Limit: limit,
	})
}

func (p *Parser) CategoryProducts(ctx context.Context, categoryInput string, limit int) ([]models.Product, error) {
	categoryInput = strings.TrimSpace(categoryInput)

	if categoryInput == "" {
		return nil, fmt.Errorf("category input is empty")
	}

	if limit <= 0 {
		return nil, fmt.Errorf("limit must be greater than zero")
	}

	return p.fetchCatalogProducts(ctx, CatalogRequest{
		Mode:  "category",
		Input: categoryInput,
		Limit: limit,
	})
}

func (p *Parser) currentCookie() string {
	if p == nil {
		return ""
	}

	if p.cookieProvider != nil {
		return strings.TrimSpace(p.cookieProvider.GetCookie())
	}

	return strings.TrimSpace(p.cookie)
}

func (p *Parser) hasCookie() bool {
	return strings.TrimSpace(p.currentCookie()) != ""
}

func (p *Parser) cookieSource() string {
	if p == nil {
		return ""
	}

	if p.cookieProvider != nil {
		return p.cookieProvider.Source()
	}

	if strings.TrimSpace(p.cookie) != "" {
		return "env"
	}

	return "empty"
}
