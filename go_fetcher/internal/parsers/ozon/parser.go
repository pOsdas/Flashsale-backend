package ozon

import (
	"context"
	"encoding/json"
	"fmt"
	"go_fetcher/internal/models"
	"html"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
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

//func debugOzonWidgetStates(widgetStates map[string]string) {
//	fmt.Printf("Ozon widgetStates count: %d\n", len(widgetStates))
//
//	for key, value := range widgetStates {
//		lowerKey := strings.ToLower(key)
//		lowerValue := strings.ToLower(value)
//
//		if strings.Contains(lowerKey, "price") ||
//			strings.Contains(lowerKey, "sku") ||
//			strings.Contains(lowerKey, "product") ||
//			strings.Contains(lowerKey, "title") ||
//			strings.Contains(lowerKey, "heading") ||
//			strings.Contains(lowerKey, "order") ||
//			strings.Contains(lowerValue, "sku") ||
//			strings.Contains(lowerValue, "price") ||
//			strings.Contains(lowerValue, "name") ||
//			strings.Contains(lowerValue, "title") {
//			fmt.Println("========== WIDGET ==========")
//			fmt.Println("KEY:", key)
//
//			if len(value) > 1000 {
//				fmt.Println("VALUE:", value[:1000])
//			} else {
//				fmt.Println("VALUE:", value)
//			}
//		}
//	}
//}

func (p *Parser) SearchProducts(ctx context.Context, query string, limit int) ([]models.Product, error) {
	return nil, fmt.Errorf("ozon search parser is not implemented yet: need real Ozon search endpoint")
}

func (p *Parser) CategoryProducts(ctx context.Context, categoryName string, limit int) ([]models.Product, error) {
	return nil, fmt.Errorf("ozon category parser is not implemented yet: need real Ozon category endpoint")
}

func (p *Parser) doJSONRequest(ctx context.Context, requestURL string, target any) error {
	var lastErr error

	for attempt := 0; attempt <= p.maxRetries; attempt++ {
		if attempt > 0 {
			delay := p.retryDelay(attempt)

			p.logger.Warn(
				"ozon request retry",
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

		if !isRetryableOzonError(err) {
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

	setOzonHeaders(req, p.cookie)

	resp, err := p.client.Do(req)
	if err != nil {
		return fmt.Errorf("execute request: %w", err)
	}
	defer resp.Body.Close()

	responseBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("read Ozon response body: %w", err)
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return &ozonHTTPError{
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

func buildProductRequestURL(productInput string) (string, string, error) {
	if strings.HasPrefix(productInput, ozonPageAPIURL) {
		parsedURL, err := url.Parse(productInput)
		if err != nil {
			return "", "", fmt.Errorf("parse Ozon API URL: %w", err)
		}

		productPath := parsedURL.Query().Get("url")
		if productPath == "" {
			return "", "", fmt.Errorf("Ozon API URL must contain url query parameter")
		}

		return productInput, productPath, nil
	}

	productPath, err := normalizeProductPath(productInput)
	if err != nil {
		return "", "", err
	}

	values := url.Values{}
	values.Set("url", productPath)

	return ozonPageAPIURL + "?" + values.Encode(), productPath, nil
}

func normalizeProductPath(productInput string) (string, error) {
	if strings.HasPrefix(productInput, "https://www.ozon.ru") ||
		strings.HasPrefix(productInput, "http://www.ozon.ru") ||
		strings.HasPrefix(productInput, "https://ozon.ru") ||
		strings.HasPrefix(productInput, "http://ozon.ru") {
		parsedURL, err := url.Parse(productInput)
		if err != nil {
			return "", fmt.Errorf("parse Ozon poduct URL: %w", err)
		}

		if !strings.HasSuffix(parsedURL.Path, "/product/") {
			return "", fmt.Errorf("Ozon product URL must start with /product/")
		}

		return ensureTrailingSlash(parsedURL.Path), nil
	}

	if strings.HasPrefix(productInput, "/product/") {
		return ensureTrailingSlash(productInput), nil
	}

	if strings.Contains(productInput, "-") {
		return ensureTrailingSlash("/product/" + productInput), nil
	}

	return "", fmt.Errorf("product input must be full Ozon product URL, /product/... path, or product slug with id")
}

func ensureTrailingSlash(value string) string {
	if strings.HasSuffix(value, "/") {
		return value
	}

	return value + "/"
}

func extractProductID(productPath string) string {
	productPath = strings.Trim(productPath, "/")
	parts := strings.Split(productPath, "-")

	if len(parts) == 0 {
		return ""
	}

	lastPart := parts[len(parts)-1]
	lastPart = strings.Trim(lastPart, "/")

	if isDigitsOnly(lastPart) {
		return lastPart
	}

	re := regexp.MustCompile(`\d+`)
	matches := re.FindAllString(productPath, -1)
	if len(matches) == 0 {
		return ""
	}

	return matches[len(matches)-1]
}

func isDigitsOnly(s string) bool {
	for _, r := range s {
		if r < '0' || r > '9' {
			return false
		}
	}

	return true
}

func extractProductsFromWidgetStates(widgetStates map[string]string) []models.Product {
	result := make([]models.Product, 0)

	mainProduct, ok := extractMainProductFromWidgetStates(widgetStates)
	if ok {
		result = append(result, mainProduct)
	}

	for _, rawWidgetState := range widgetStates {
		var decoded any

		if err := json.Unmarshal([]byte(rawWidgetState), &decoded); err != nil {
			continue
		}

		tiles := findOzonProductTiles(decoded)

		for _, tile := range tiles {
			product, ok := normalizeOzonProductTile(tile)
			if !ok {
				continue
			}

			result = append(result, product)
		}
	}

	return result
}

func extractMainProductFromWidgetStates(widgetStates map[string]string) (models.Product, bool) {
	mainSKU := ""
	mainURL := ""

	for key, rawWidgetState := range widgetStates {
		if !strings.Contains(key, "webProductMainWidget") {
			continue
		}

		var mainWidget ozonMainProductWidget

		if err := json.Unmarshal([]byte(rawWidgetState), &mainWidget); err != nil {
			continue
		}

		mainSKU = strings.TrimSpace(mainWidget.SKU)
		mainURL = strings.TrimSpace(mainWidget.URL)
		break
	}

	if mainSKU == "" {
		return models.Product{}, false
	}

	if aspectProduct, ok := extractProductFromAspects(widgetStates, mainSKU); ok {
		return aspectProduct, true
	}

	title := buildTitleFromOzonProductURL(mainURL)
	if title == "" {
		title = mainSKU
	}

	return models.Product{
		SKU:        mainSKU,
		Title:      title,
		PriceCents: 0,
		Currency:   defaultCurrency,
		Available:  1,
		IsActive:   true,
	}, true
}

func extractProductFromAspects(widgetStates map[string]string, targetSKU string) (models.Product, bool) {
	for key, rawWidgetState := range widgetStates {
		if !strings.Contains(key, "webAspects") {
			continue
		}

		var aspectsWidget ozonAspectsWidget

		if err := json.Unmarshal([]byte(rawWidgetState), &aspectsWidget); err != nil {
			continue
		}

		for _, aspect := range aspectsWidget.Aspects {
			for _, variant := range aspect.Variants {
				if variant.SKU != targetSKU {
					continue
				}

				title := strings.TrimSpace(variant.Data.Title)
				title = html.UnescapeString(title)
				title = stripHTMLTags(title)

				if title == "" {
					title = targetSKU
				}

				priceCents := 0
				if variant.Price > 0 {
					priceCents = variant.Price * 100
				} else {
					priceRubles := parsePriceRubles(variant.Data.Price)
					priceCents = priceRubles * 100
				}

				available := 0
				if variant.Availability == "inStock" {
					available = 1
				}

				return models.Product{
					SKU:        targetSKU,
					Title:      title,
					PriceCents: priceCents,
					Currency:   defaultCurrency,
					Available:  available,
					IsActive:   true,
				}, true
			}
		}
	}

	return models.Product{}, false
}

func buildTitleFromOzonProductURL(productURL string) string {
	productURL = strings.TrimSpace(productURL)
	productURL = strings.Trim(productURL, "/")

	if productURL == "" {
		return ""
	}

	parts := strings.Split(productURL, "/")
	if len(parts) == 0 {
		return ""
	}

	slug := parts[len(parts)-1]
	if slug == "" {
		return ""
	}

	slugParts := strings.Split(slug, "-")
	if len(slugParts) > 1 && isDigitsOnly(slugParts[len(slugParts)-1]) {
		slugParts = slugParts[:len(slugParts)-1]
	}

	title := strings.Join(slugParts, " ")
	title = strings.TrimSpace(title)

	return title
}

func findOzonProductTiles(value any) []ozonProductTile {
	result := make([]ozonProductTile, 0)

	switch typed := value.(type) {
	case map[string]any:
		if _, hasSKU := typed["skuId"]; hasSKU {
			rawBytes, err := json.Marshal(typed)
			if err == nil {
				var tile ozonProductTile
				if err := json.Unmarshal(rawBytes, &tile); err == nil && tile.SKUID != "" {
					result = append(result, tile)
				}
			}
		}

		for _, nestedValue := range typed {
			result = append(result, findOzonProductTiles(nestedValue)...)
		}

	case []any:
		for _, item := range typed {
			result = append(result, findOzonProductTiles(item)...)
		}
	}

	return result
}

func normalizeOzonProductTile(tile ozonProductTile) (models.Product, bool) {
	sku := strings.TrimSpace(tile.SKUID)
	if sku == "" {
		return models.Product{}, false
	}

	title := extractTitleFromTile(tile)
	if title == "" {
		return models.Product{}, false
	}

	priceCents := extractPriceCentsFromTile(tile)
	if priceCents <= 0 {
		return models.Product{}, false
	}

	available := extractAvailableFromTile(tile)
	if available <= 0 {
		available = 1
	}

	return models.Product{
		SKU:        sku,
		Title:      title,
		PriceCents: priceCents,
		Currency:   defaultCurrency,
		Available:  available,
		IsActive:   true,
	}, true
}

func extractTitleFromTile(tile ozonProductTile) string {
	for _, item := range tile.State {
		if item.Type != "textAtom" {
			continue
		}

		if item.ID != "name" {
			continue
		}

		title := strings.TrimSpace(item.TextAtom.Text)
		title = html.UnescapeString(title)
		title = stripHTMLTags(title)

		if title != "" {
			return title
		}
	}

	alt := strings.TrimSpace(tile.Alt)
	alt = html.UnescapeString(alt)
	alt = stripHTMLTags(alt)

	return alt
}

func extractPriceCentsFromTile(tile ozonProductTile) int {
	for _, item := range tile.State {
		if item.Type != "priceV2" {
			continue
		}

		for _, priceItem := range item.PriceV2.Price {
			if priceItem.TextStyle != "PRICE" {
				continue
			}

			priceRubles := parsePriceRubles(priceItem.Text)
			if priceRubles > 0 {
				return priceRubles * 100
			}
		}

		for _, priceItem := range item.PriceV2.Price {
			priceRubles := parsePriceRubles(priceItem.Text)
			if priceRubles > 0 {
				return priceRubles * 100
			}
		}
	}

	return 0
}

func extractAvailableFromTile(tile ozonProductTile) int {
	for _, item := range tile.State {
		if item.Type != "textAtom" {
			continue
		}

		text := strings.ToLower(item.TextAtom.Text)

		if !strings.Contains(text, "осталось") {
			continue
		}

		quantity := parseFirstInt(text)
		if quantity > 0 {
			return quantity
		}
	}

	if tile.Button.AddToCartButtonWithQuantity.MaxItems > 0 {
		return tile.Button.AddToCartButtonWithQuantity.MaxItems
	}

	return 0
}

func parsePriceRubles(rawPrice string) int {
	cleaned := strings.TrimSpace(rawPrice)
	cleaned = html.UnescapeString(cleaned)
	cleaned = strings.ReplaceAll(cleaned, "\u2009", "")
	cleaned = strings.ReplaceAll(cleaned, "\u00a0", "")
	cleaned = strings.ReplaceAll(cleaned, " ", "")
	cleaned = strings.ReplaceAll(cleaned, "₽", "")
	cleaned = strings.ReplaceAll(cleaned, "р.", "")
	cleaned = strings.ReplaceAll(cleaned, "руб.", "")
	cleaned = strings.ReplaceAll(cleaned, ",", ".")
	cleaned = strings.TrimSpace(cleaned)

	if cleaned == "" {
		return 0
	}

	if strings.Contains(cleaned, ".") {
		parts := strings.Split(cleaned, ".")
		cleaned = parts[0]
	}

	value, err := strconv.Atoi(cleaned)
	if err != nil {
		return 0
	}

	return value
}

func parseFirstInt(rawText string) int {
	re := regexp.MustCompile(`\d+`)
	match := re.FindString(rawText)
	if match == "" {
		return 0
	}

	value, err := strconv.Atoi(match)
	if err != nil {
		return 0
	}

	return value
}

func stripHTMLTags(value string) string {
	re := regexp.MustCompile(`<[^>]*>`)
	return strings.TrimSpace(re.ReplaceAllString(value, ""))
}

func findProductBySKU(products []models.Product, sku string) *models.Product {
	for index := range products {
		if products[index].SKU == sku {
			return &products[index]
		}
	}

	return nil
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

func setOzonHeaders(req *http.Request, cookie string) {
	req.Header.Set("Accept", "application/json, text/plain, */*")
	req.Header.Set("Accept-Language", "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7")
	req.Header.Set("Connection", "keep-alive")
	req.Header.Set("Referer", "https://www.ozon.ru/")
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

func isRetryableOzonError(err error) bool {
	httpErr, ok := err.(*ozonHTTPError)
	if !ok {
		return false
	}

	return httpErr.StatusCode == http.StatusTooManyRequests ||
		httpErr.StatusCode == 403 ||
		httpErr.StatusCode >= 503
}

type ozonHTTPError struct {
	StatusCode int
	Body       string
}

func (e *ozonHTTPError) Error() string {
	return fmt.Sprintf("unexpected Ozon status code: %d, body: %s", e.StatusCode, e.Body)
}

type ozonMainProductWidget struct {
	SKU string `json:"sku"`
	URL string `json:"url"`
}

type ozonPageResponse struct {
	WidgetStates map[string]string `json:"widgetStates"`
}

type ozonShelfWidget struct {
	ProductContainer ozonProductContainer `json:"productContainer"`
}

type ozonProductContainer struct {
	Products []ozonProductTile `json:"products"`
}

type ozonProductTile struct {
	SKUID  string            `json:"skuId"`
	Alt    string            `json:"alt"`
	Link   string            `json:"link"`
	Button ozonProductButton `json:"button"`
	State  []ozonTileState   `json:"state"`
}

type ozonProductButton struct {
	AddToCartButtonWithQuantity ozonAddToCartButtonWithQuantity `json:"addToCartButtonWithQuantity"`
}

type ozonAddToCartButtonWithQuantity struct {
	MaxItems     int `json:"maxItems"`
	CurrentItems int `json:"currentItems"`
}

type ozonTileState struct {
	Type     string       `json:"type"`
	ID       string       `json:"id"`
	TextAtom ozonTextAtom `json:"textAtom"`
	PriceV2  ozonPriceV2  `json:"priceV2"`
}

type ozonTextAtom struct {
	Text string `json:"text"`
}

type ozonPriceV2 struct {
	Price []ozonPriceItem `json:"price"`
}

type ozonPriceItem struct {
	Text      string `json:"text"`
	TextStyle string `json:"textStyle"`
}

type ozonAspectsWidget struct {
	Aspects []ozonAspect `json:"aspects"`
}

type ozonAspect struct {
	Variants []ozonAspectVariant `json:"variants"`
}

type ozonAspectVariant struct {
	SKU          string                `json:"sku"`
	Availability string                `json:"availability"`
	Price        int                   `json:"price"`
	Data         ozonAspectVariantData `json:"data"`
}

type ozonAspectVariantData struct {
	Title string `json:"title"`
	Price string `json:"price"`
}
