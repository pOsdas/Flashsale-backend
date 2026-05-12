package wildberries

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"

	"go_fetcher/internal/models"
)

type Parser struct {
	httpClient *http.Client
}

type wbCardResponse struct {
	Products []wbProduct `json:"products"`
}

type wbProduct struct {
	ID            int64    `json:"id"`
	Name          string   `json:"name"`
	TotalQuantity int      `json:"totalQuantity"`
	Sizes         []wbSize `json:"sizes"`
}

type wbSize struct {
	Stocks []wbStock `json:"stocks"`
	Price  wbPrice   `json:"price"`
}

type wbStock struct {
	Qty int `json:"qty"`
}

type wbPrice struct {
	Basic   int `json:"basic"`
	Product int `json:"product"`
}

func NewParser() *Parser {
	return &Parser{
		httpClient: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
}

func (p *Parser) ParseProduct(ctx context.Context, productID string) (*models.Product, error) {
	if productID == "" {
		return nil, fmt.Errorf("product id is required")
	}

	var body []byte
	var lastErr error

	for _, productURL := range buildCardURLs(productID) {
		fmt.Println("Trying Wildberries product URL:", productURL)

		body, lastErr = p.fetchJSON(ctx, productURL)
		if lastErr == nil {
			break
		}

		fmt.Println("Wildberries URL failed:", lastErr)
	}

	if body == nil {
		return nil, fmt.Errorf(
			"failed to fetch wildberries product %s: %w",
			productID,
			lastErr,
		)
	}

	var response wbCardResponse

	if err := json.Unmarshal(body, &response); err != nil {
		return nil, fmt.Errorf("failed to decode wildberries response: %w", err)
	}

	if len(response.Products) == 0 {
		return nil, fmt.Errorf(
			"wildberries product not found: %s",
			productID,
		)
	}

	wbProduct := response.Products[0]

	available := wbProduct.TotalQuantity
	if available == 0 {
		for _, size := range wbProduct.Sizes {
			for _, stock := range size.Stocks {
				available += stock.Qty
			}
		}
	}

	priceCents := 0
	if len(wbProduct.Sizes) > 0 {
		priceCents = wbProduct.Sizes[0].Price.Product

		if priceCents == 0 {
			priceCents = wbProduct.Sizes[0].Price.Basic
		}
	}

	product := &models.Product{
		SKU:        fmt.Sprintf("WB-%d", wbProduct.ID),
		Title:      wbProduct.Name,
		PriceCents: priceCents,
		Currency:   "RUB",
		Available:  available,
		IsActive:   true,
	}

	return product, nil
}

func (p *Parser) fetchJSON(ctx context.Context, url string) ([]byte, error) {
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		url,
		nil,
	)
	if err != nil {
		return nil, fmt.Errorf("error creating request: %w", err)
	}

	request.Header.Set("Accept", "application/json, text/plain, */*")
	request.Header.Set("Accept-Language", "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7")
	request.Header.Set("Referer", "https://www.wildberries.ru/catalog/302421341/detail.aspx")
	request.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")

	wbCookie := os.Getenv("WB_COOKIE")
	if wbCookie != "" {
		request.Header.Set("Cookie", wbCookie)
	}

	response, err := p.httpClient.Do(request)
	if err != nil {
		return nil, fmt.Errorf("Failed to fetch wildberries json: %w", err)
	}
	defer response.Body.Close()

	body, err := io.ReadAll(response.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read wildberries response body: %w", err)
	}

	if response.StatusCode < 200 || response.StatusCode >= 300 {
		body, _ := io.ReadAll(response.Body)

		return nil, fmt.Errorf(
			"unexpected wildberries status code: %d, response body: %s",
			response.StatusCode,
			string(body[:minInt(len(body), 500)]),
		)
	}

	return body, nil
}

func buildCardURLs(productID string) []string {
	return []string{
		fmt.Sprintf(
			"https://www.wildberries.ru/__internal/card/cards/v4/detail?appType=1&curr=rub&dest=123589323&spp=30&hide_vflags=4294967296&mdg=100&ab_testing=false&lang=ru&nm=%s",
			productID,
		),
		fmt.Sprintf(
			"https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=123589323&spp=30&ab_testing=false&nm=%s",
			productID,
		),
	}
}

func minInt(a, b int) int {
	if a < b {
		return a
	}

	return b
}
