package wildberries

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	"go_fetcher/internal/models"
)

const (
	defaultCurrency = "RUB"

	detailURL = "https://www.wildberries.ru/__internal/card/cards/v4/detail"
	searchURL = "https://search.wb.ru/exactmatch/ru/common/v18/search"
)

type Parser struct {
	client *http.Client
}

func NewParser() *Parser {
	return &Parser{
		client: &http.Client{
			Timeout: 15 * time.Second,
		},
	}
}

func (p *Parser) ParseProduct(ctx context.Context, nmID string) ([]models.Product, error) {
	requestURL := buildDetailURL(nmID)

	var response wbProductsResponse

	if err := p.doJSONRequest(ctx, requestURL, &response); err != nil {
		return nil, fmt.Errorf("parse WB product %s: %w", nmID, err)
	}

	return normalizeWBProducts(response.Products), nil
}

func (p *Parser) SearchProducts(ctx context.Context, query string, limit int) ([]models.Product, error) {
	if strings.TrimSpace(query) == "" {
		return nil, fmt.Errorf("search query is empty")
	}

	if limit <= 0 {
		return nil, fmt.Errorf("limit must be greater than zero")
	}

	requestURL := buildSearchURL(query, limit)

	var response wbProductsResponse

	if err := p.doJSONRequest(ctx, requestURL, &response); err != nil {
		return nil, fmt.Errorf("search WB products by query %q: %w", query, err)
	}

	products := normalizeWBProducts(response.Products)

	if len(products) > limit {
		products = products[:limit]
	}

	return products, nil
}

func (p *Parser) CategoryProducts(ctx context.Context, categoryName string, limit int) ([]models.Product, error) {
	if strings.TrimSpace(categoryName) == "" {
		return nil, fmt.Errorf("category name is empty")
	}

	if limit <= 0 {
		return nil, fmt.Errorf("limit must be greater than zero")
	}

	requestURL := buildCategoryURL(categoryName)

	var response wbProductsResponse

	if err := p.doJSONRequest(ctx, requestURL, &response); err != nil {
		return nil, fmt.Errorf("parse WB category %q: %w", categoryName, err)
	}

	products := normalizeWBProducts(response.Products)

	if len(products) > limit {
		products = products[:limit]
	}

	return products, nil
}

func (p *Parser) doJSONRequest(ctx context.Context, requestURL string, target any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, requestURL, nil)
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}

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

	wbCookie := os.Getenv("WB_COOKIE")
	if wbCookie != "" {
		req.Header.Set("Cookie", wbCookie)
	}

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
		return fmt.Errorf(
			"unexpected WB status code: %d, body: %s",
			resp.StatusCode,
			string(responseBody),
		)
	}

	if err := json.Unmarshal(responseBody, target); err != nil {
		return fmt.Errorf("decode response: %w, body: %s", err, string(responseBody))
	}

	return nil
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

func buildSearchURL(query string, limit int) string {
	values := url.Values{}

	values.Set("ab_testid", "catboost_exp_2")
	values.Set("appType", "1")
	values.Set("curr", "rub")
	values.Set("dest", "123589323")
	values.Set("hide_vflags", "4294967296")
	values.Set("inheritFilters", "false")
	values.Set("lang", "ru")
	values.Set("locale", "ru")
	values.Set("mdg", "100")
	values.Set("query", query)
	values.Set("resultset", "catalog")
	values.Set("sort", "popular")
	values.Set("spp", "30")
	values.Set("suppressSpellcheck", "false")
	values.Set("uclusters", "2")

	baseURL := "https://www.wildberries.ru/__internal/search/exactmatch/ru/common/v18/search"

	return baseURL + "?" + values.Encode()

}

func buildCategoryURL(categoryName string) string {
	categoryQuery := fmt.Sprintf(
		"menu_redirect_subject_v2_9973_corr %s",
		strings.TrimSpace(categoryName),
	)

	values := url.Values{}

	values.Set("ab_testid", "catboost_exp_2")
	values.Set("appType", "1")
	values.Set("curr", "rub")
	values.Set("dest", "123589323")
	values.Set("hide_vflags", "4294967296")
	values.Set("lang", "ru")
	values.Set("locale", "ru")
	values.Set("mdg", "110")
	values.Set("query", categoryQuery)
	values.Set("resultset", "catalog")
	values.Set("sort", "popular")
	values.Set("spp", "30")
	values.Set("suppressSpellcheck", "false")
	values.Set("uclusters", "2")

	baseURL := "https://www.wildberries.ru/__internal/search/exactmatch/ru/common/v18/search"

	return baseURL + "?" + values.Encode()
}

func extractCategoryParams(categoryURL string) (string, string, error) {
	parsedURL, err := url.Parse(categoryURL)
	if err != nil {
		return "", "", fmt.Errorf("parse category URL: %w", err)
	}

	query := parsedURL.RawQuery
	if query == "" {
		return "", "", fmt.Errorf("category URL must contain WB catalog query params from Network request")
	}

	shard := parsedURL.Query().Get("shard")
	if shard == "" {
		shard = "preset"
	}

	return shard, query, nil
}

func parseRawQuery(rawQuery string) map[string]string {
	result := make(map[string]string)

	values, err := url.ParseQuery(rawQuery)
	if err != nil {
		return result
	}

	for key, value := range values {
		if len(value) > 0 {
			result[key] = value[0]
		}
	}

	return result
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

	if len(product.Sizes) > 0 && product.Sizes[0].Price.Total > 0 {
		return product.Sizes[0].Price.Total
	}

	return 0
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
	Total int `json:"total"`
}
