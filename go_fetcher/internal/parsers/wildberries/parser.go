package wildberries

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"strconv"
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

func (p *Parser) fetchCatalogProducts(
	ctx context.Context,
	mode string,
	query string,
	limit int,
	buildURL func(page int) string,
) ([]models.Product, error) {
	collected := make([]models.Product, 0, limit)
	seen := make(map[string]struct{})

	totalPages := calculatePages(limit, defaultPageSize)

	for page := 1; page <= totalPages; page++ {
		requestURL := buildURL(page)

		var response wbProductsResponse

		if err := p.doJSONRequest(ctx, requestURL, &response); err != nil {
			return nil, fmt.Errorf("fetch page %d: %w", page, err)
		}

		pageProducts := normalizeWBProducts(response.Products)

		addedOnPage := 0

		for _, product := range pageProducts {
			if len(collected) >= limit {
				break
			}

			if product.SKU == "" {
				continue
			}

			if _, exists := seen[product.SKU]; exists {
				continue
			}

			seen[product.SKU] = struct{}{}
			collected = append(collected, product)
			addedOnPage++
		}

		p.logger.Info(
			"wildberries page parsed",
			slog.String("mode", mode),
			slog.String("query", query),
			slog.Int("page", page),
			slog.Int("received", len(pageProducts)),
			slog.Int("added", addedOnPage),
			slog.Int("collected", len(collected)),
			slog.Int("limit", limit),
		)

		if len(collected) >= limit {
			break
		}

		if len(pageProducts) == 0 {
			break
		}
	}

	return collected, nil
}

func (p *Parser) doJSONRequest(ctx context.Context, requestURL string, target any) error {
	var lastErr error

	for attempt := 0; attempt <= p.maxRetries; attempt++ {
		if attempt > 0 {
			delay := p.retryDelay(attempt)

			p.logger.Warn(
				"wildberries request retry",
				slog.Int("attempt", attempt),
				slog.Duration("delay", delay),
				slog.String("url", requestURL),
				slog.String("error", lastErr.Error()),
			)

			if err := sleepWithContext(ctx, delay); err != nil {
				return err
			}
		} else if p.requestDelay > 0 {
			if err := sleepWithContext(ctx, p.requestDelay); err != nil {
				return err
			}
		}

		err := p.doJSONRequestOnce(ctx, requestURL, target)
		if err == nil {
			return nil
		}

		lastErr = err

		if !isRetryableWBError(err) {
			return err
		}
	}

	return fmt.Errorf("request failed after %d retries: %w", p.maxRetries, lastErr)
}

func (p *Parser) doJSONRequestOnce(ctx context.Context, requestURL string, target any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, requestURL, nil)
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}

	setWBHeaders(req, p.cookie)

	resp, err := p.client.Do(req)
	if err != nil {
		return fmt.Errorf("execute request: %w", err)
	}
	defer resp.Body.Close()

	responseBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("read WB response body: %w", err)
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return &wbHTTPError{
			StatusCode: resp.StatusCode,
			Body:       string(responseBody),
		}
	}

	if err := json.Unmarshal(responseBody, target); err != nil {
		return fmt.Errorf("decode response: %w, body: %s", err, string(responseBody))
	}

	return nil
}

func (p *Parser) retryDelay(attempt int) time.Duration {
	multiplier := 1 << (attempt - 1)
	return time.Duration(multiplier) * p.retryBaseDelay
}

func setWBHeaders(req *http.Request, cookie string) {
	req.Header.Set("Accept", "application/json, text/plain, */*")
	req.Header.Set("Accept-Language", "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7")
	req.Header.Set("Connection", "keep-alive")
	req.Header.Set("Referer", "https://www.wildberries.ru/catalog/0/search.aspx?search=iphone")
	req.Header.Set("Sec-Fetch-Dest", "empty")
	req.Header.Set("Sec-Fetch-Mode", "cors")
	req.Header.Set("Sec-Fetch-Site", "same-origin")
	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")
	req.Header.Set("sec-ch-ua", `"Chromium";v="148", "Google Chrome";v="148", "Not-A.Brand";v="99"`)
	req.Header.Set("sec-ch-ua-mobile", "?0")
	req.Header.Set("sec-ch-ua-platform", `"Windows"`)

	if cookie != "" {
		req.Header.Set("Cookie", cookie)
	}
}

func buildDetailURL(nmID string) string {
	values := url.Values{}
	values.Set("appType", "1")
	values.Set("curr", "rub")
	values.Set("dest", "-1257786")
	values.Set("spp", "30")
	values.Set("hide_dtype", "10")
	values.Set("ab_testing", "false")
	values.Set("lang", "ru")
	values.Set("nm", nmID)

	return detailURL + "?" + values.Encode()
}

func buildSearchURL(query string, page int) string {
	values := buildBaseCatalogQuery(page)
	values.Set("mdg", "100")
	values.Set("query", query)

	return catalogURL + "?" + values.Encode()
}

func buildCategoryURL(categoryName string, page int) string {
	categoryQuery := fmt.Sprintf(
		"menu_redirect_subject_v2_9973_corr %s",
		strings.TrimSpace(categoryName),
	)

	values := buildBaseCatalogQuery(page)
	values.Set("mdg", "110")
	values.Set("query", categoryQuery)

	return catalogURL + "?" + values.Encode()
}

func buildBaseCatalogQuery(page int) url.Values {
	values := url.Values{}

	values.Set("ab_testid", "catboost_exp_2")
	values.Set("appType", "1")
	values.Set("curr", "rub")
	values.Set("dest", "123589323")
	values.Set("hide_vflags", "4294967296")
	values.Set("inheritFilters", "false")
	values.Set("lang", "ru")
	values.Set("locale", "ru")
	values.Set("page", strconv.Itoa(page))
	values.Set("resultset", "catalog")
	values.Set("sort", "popular")
	values.Set("spp", "30")
	values.Set("suppressSpellcheck", "false")
	values.Set("uclusters", "2")

	return values
}

func normalizeWBProducts(products []wbProduct) []models.Product {
	result := make([]models.Product, 0, len(products))

	for _, product := range products {
		normalized := models.Product{
			SKU:        strconv.FormatInt(product.ID, 10),
			Title:      buildProductTitle(product),
			PriceCents: extractPriceCents(product),
			Currency:   defaultCurrency,
			Available:  product.TotalQuantity,
			IsActive:   true,
		}

		if normalized.SKU == "" || normalized.Title == "" {
			continue
		}

		result = append(result, normalized)
	}

	return result
}

func deduplicateProductsBySKU(products []models.Product) []models.Product {
	result := make([]models.Product, 0, len(products))
	seen := make(map[string]struct{}, len(products))

	for _, product := range products {
		if product.SKU == "" {
			continue
		}

		if _, exists := seen[product.SKU]; exists {
			continue
		}

		seen[product.SKU] = struct{}{}
		result = append(result, product)
	}

	return result
}

func buildProductTitle(product wbProduct) string {
	brand := strings.TrimSpace(product.Brand)
	name := strings.TrimSpace(product.Name)

	switch {
	case brand != "" && name != "":
		return brand + " " + name
	case name != "":
		return name
	case brand != "":
		return brand
	default:
		return strconv.FormatInt(product.ID, 10)
	}
}

func extractPriceCents(product wbProduct) int {
	if product.SalePriceU > 0 {
		return product.SalePriceU
	}

	if product.PriceU > 0 {
		return product.PriceU
	}

	if len(product.Sizes) > 0 && product.Sizes[0].Price.Product > 0 {
		return product.Sizes[0].Price.Product
	}

	if len(product.Sizes) > 0 && product.Sizes[0].Price.Total > 0 {
		return product.Sizes[0].Price.Total
	}

	if len(product.Sizes) > 0 && product.Sizes[0].Price.Basic > 0 {
		return product.Sizes[0].Price.Basic
	}

	return 0
}

func calculatePages(limit int, pageSize int) int {
	if limit <= 0 {
		return 1
	}

	pages := limit / pageSize
	if limit%pageSize != 0 {
		pages++
	}

	if pages == 0 {
		return 1
	}

	return pages
}

func sleepWithContext(ctx context.Context, delay time.Duration) error {
	timer := time.NewTimer(delay)
	defer timer.Stop()

	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

func isRetryableWBError(err error) bool {
	httpErr, ok := err.(*wbHTTPError)
	if !ok {
		return false
	}

	return httpErr.StatusCode == http.StatusTooManyRequests ||
		httpErr.StatusCode == 498 ||
		httpErr.StatusCode >= 500
}

type wbHTTPError struct {
	StatusCode int
	Body       string
}

func (e *wbHTTPError) Error() string {
	return fmt.Sprintf("unexpected WB status code: %d, body: %s", e.StatusCode, e.Body)
}

type wbProductsResponse struct {
	Products []wbProduct `json:"products"`
}

type wbProduct struct {
	ID            int64    `json:"id"`
	Brand         string   `json:"brand"`
	Name          string   `json:"name"`
	PriceU        int      `json:"priceU"`
	SalePriceU    int      `json:"salePriceU"`
	TotalQuantity int      `json:"totalQuantity"`
	Sizes         []wbSize `json:"sizes"`
}

type wbSize struct {
	Price wbPrice `json:"price"`
}

type wbPrice struct {
	Basic   int `json:"basic"`
	Product int `json:"product"`
	Total   int `json:"total"`
}
