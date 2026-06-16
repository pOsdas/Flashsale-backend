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
	ozonUserAgent  = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0"
)

type Parser struct {
	client         *http.Client
	browserClient  *BrowserClient
	logger         *slog.Logger
	cookie         string
	cookieProvider cookies.Provider
	requestDelay   time.Duration
	maxRetries     int
	retryBaseDelay time.Duration
}

type ParserConfig struct {
	Cookie                string
	CookieProvider        cookies.Provider
	Timeout               time.Duration
	RequestDelay          time.Duration
	MaxRetries            int
	RetryBaseDelay        time.Duration
	BrowserFetcherURL     string
	BrowserFetcherEnabled bool
	BrowserFetcherTimeout time.Duration
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
			Timeout:   cfg.Timeout,
			Transport: newOzonHTTPTransport(),
		},
		browserClient:  NewBrowserClient(cfg.BrowserFetcherEnabled, cfg.BrowserFetcherURL, cfg.BrowserFetcherTimeout, logger),
		logger:         logger,
		cookie:         cfg.Cookie,
		cookieProvider: cfg.CookieProvider,
		requestDelay:   cfg.RequestDelay,
		maxRetries:     cfg.MaxRetries,
		retryBaseDelay: cfg.RetryBaseDelay,
	}
}

func (p *Parser) ParseProduct(ctx context.Context, productInput string) ([]models.Product, error) {
	products, err := p.parseProductHTTP(ctx, productInput)
	if err == nil && isValidOzonProductList(products) {
		return products, nil
	}

	if !p.shouldUseBrowserFallback(productInput, err, products) {
		return products, err
	}

	p.logBrowserFallbackStart("product", productInput, 1, ozonBrowserProductPath, err, products)

	product, browserErr := p.browserClient.ParseProduct(ctx, productInput)
	if browserErr != nil {
		p.logBrowserFallbackFailure("product", productInput, ozonBrowserProductPath, browserErr)

		if err != nil {
			return nil, fmt.Errorf("parse Ozon product with HTTP failed: %w; browser fallback failed: %w", err, browserErr)
		}

		return products, fmt.Errorf("parse Ozon product with browser fallback: %w", browserErr)
	}

	return []models.Product{product}, nil
}

func (p *Parser) parseProductHTTP(ctx context.Context, productInput string) ([]models.Product, error) {
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

func (p *Parser) shouldUseBrowserFallback(productInput string, err error, products []models.Product) bool {
	if p == nil || p.browserClient == nil || !p.browserClient.Enabled() {
		return false
	}

	if strings.TrimSpace(productInput) == "" {
		return false
	}

	return err != nil || !isValidOzonProductList(products)
}

func isValidOzonProductList(products []models.Product) bool {
	if len(products) == 0 {
		return false
	}

	for _, product := range products {
		if !isValidOzonProduct(product) {
			return false
		}
	}

	return true
}

func isValidOzonProduct(product models.Product) bool {
	return strings.TrimSpace(product.SKU) != "" &&
		strings.TrimSpace(product.Title) != "" &&
		product.PriceCents > 0 &&
		strings.TrimSpace(product.Currency) != ""
}

func (p *Parser) SearchProducts(ctx context.Context, query string, limit int) ([]models.Product, error) {
	query = strings.TrimSpace(query)

	if query == "" {
		return nil, fmt.Errorf("search query is empty")
	}

	if limit <= 0 {
		return nil, fmt.Errorf("limit must be greater than zero")
	}

	products, err := p.fetchCatalogProducts(ctx, CatalogRequest{
		Mode:  "search",
		Input: query,
		Limit: limit,
	})
	if err == nil && isValidOzonProductList(products) {
		return products, nil
	}

	if !p.shouldUseBrowserFallback(query, err, products) {
		return products, err
	}

	p.logBrowserFallbackStart("search", query, limit, ozonBrowserSearchPath, err, products)

	browserProducts, browserErr := p.browserClient.SearchProducts(ctx, query, limit)
	if browserErr != nil {
		p.logBrowserFallbackFailure("search", query, ozonBrowserSearchPath, browserErr)

		if err != nil {
			return nil, fmt.Errorf("search Ozon products with HTTP failed: %w; browser fallback failed: %w", err, browserErr)
		}

		return products, fmt.Errorf("search Ozon products with browser fallback: %w", browserErr)
	}

	return browserProducts, nil
}

func (p *Parser) CategoryProducts(ctx context.Context, categoryInput string, limit int) ([]models.Product, error) {
	categoryInput = strings.TrimSpace(categoryInput)

	if categoryInput == "" {
		return nil, fmt.Errorf("category input is empty")
	}

	if limit <= 0 {
		return nil, fmt.Errorf("limit must be greater than zero")
	}

	products, err := p.fetchCatalogProducts(ctx, CatalogRequest{
		Mode:  "category",
		Input: categoryInput,
		Limit: limit,
	})
	if err == nil && isValidOzonProductList(products) {
		return products, nil
	}

	if !p.shouldUseBrowserFallback(categoryInput, err, products) {
		return products, err
	}

	p.logBrowserFallbackStart("category", categoryInput, limit, ozonBrowserCategoryPath, err, products)

	browserProducts, browserErr := p.browserClient.CategoryProducts(ctx, categoryInput, limit)
	if browserErr != nil {
		p.logBrowserFallbackFailure("category", categoryInput, ozonBrowserCategoryPath, browserErr)

		if err != nil {
			return nil, fmt.Errorf("parse Ozon category with HTTP failed: %w; browser fallback failed: %w", err, browserErr)
		}

		return products, fmt.Errorf("parse Ozon category with browser fallback: %w", browserErr)
	}

	return browserProducts, nil
}

func (p *Parser) logBrowserFallbackStart(mode string, input string, limit int, endpointPath string, err error, products []models.Product) {
	attrs := []slog.Attr{
		slog.String("mode", mode),
		slog.String("input", input),
		slog.Int("limit", limit),
		slog.String("endpoint", p.browserFallbackEndpoint(endpointPath)),
		slog.Int("products_count", len(products)),
		slog.Int("invalid_products_count", countInvalidOzonProducts(products)),
	}

	if err != nil {
		attrs = append(
			attrs,
			slog.String("reason", "go_parser_error"),
			slog.String("go_parser_error", err.Error()),
		)
	} else {
		attrs = append(attrs, slog.String("reason", "invalid_or_empty_products"))
	}

	p.logger.LogAttrs(
		context.Background(),
		slog.LevelWarn,
		"ozon browser fallback started",
		attrs...,
	)
}

func (p *Parser) logBrowserFallbackFailure(mode string, input string, endpointPath string, err error) {
	p.logger.Error(
		"ozon browser fallback failed",
		slog.String("mode", mode),
		slog.String("input", input),
		slog.String("endpoint", p.browserFallbackEndpoint(endpointPath)),
		slog.String("error", err.Error()),
	)
}

func (p *Parser) browserFallbackEndpoint(endpointPath string) string {
	if p == nil || p.browserClient == nil || !p.browserClient.Enabled() {
		return ""
	}

	return p.browserClient.endpointFor(endpointPath)
}

func countInvalidOzonProducts(products []models.Product) int {
	invalidProducts := 0

	for _, product := range products {
		if !isValidOzonProduct(product) {
			invalidProducts++
		}
	}

	return invalidProducts
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

func newOzonHTTPTransport() http.RoundTripper {
	return &http.Transport{
		Proxy: http.ProxyFromEnvironment,

		MaxIdleConns:        100,
		MaxIdleConnsPerHost: 10,
		IdleConnTimeout:     90 * time.Second,

		TLSHandshakeTimeout:   10 * time.Second,
		ResponseHeaderTimeout: 20 * time.Second,
		ExpectContinueTimeout: 1 * time.Second,

		ForceAttemptHTTP2: true,
	}
}
