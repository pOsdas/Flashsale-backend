package wildberries

import (
	"fmt"
	"strings"
	"unicode"

	"go_fetcher/internal/models"
)

func validateWBProductResponse(response wbProductsResponse, requestedNMID string) ([]models.Product, error) {
	requestedNMID = strings.TrimSpace(requestedNMID)
	if requestedNMID == "" {
		return nil, fmt.Errorf("requested WB nm_id is empty")
	}

	products := deduplicateProductsBySKU(normalizeWBProducts(response.productList()))
	for _, product := range products {
		if product.SKU != requestedNMID {
			continue
		}
		if err := validateWBProduct(product, requestedNMID, product.Available > 0); err != nil {
			return nil, err
		}
		return []models.Product{product}, nil
	}

	if len(products) == 0 {
		return nil, fmt.Errorf("WB product response contains no products for requested nm_id %s", requestedNMID)
	}

	return nil, fmt.Errorf(
		"WB product response nm_id mismatch: requested %s, parsed %s",
		requestedNMID,
		products[0].SKU,
	)
}

func validateWBProduct(product models.Product, requestedNMID string, requirePrice bool) error {
	if strings.TrimSpace(product.SKU) == "" {
		return fmt.Errorf("WB product SKU is empty")
	}
	if strings.TrimSpace(product.SKU) != strings.TrimSpace(requestedNMID) {
		return fmt.Errorf("WB product SKU mismatch: requested %s, parsed %s", requestedNMID, product.SKU)
	}
	if strings.TrimSpace(product.Title) == "" {
		return fmt.Errorf("WB product title is empty for nm_id %s", requestedNMID)
	}
	if isGenericWBTitle(product.Title) {
		return fmt.Errorf("WB product title is a generic marketplace title for nm_id %s: %q", requestedNMID, product.Title)
	}
	if requirePrice && product.PriceCents <= 0 {
		return fmt.Errorf("WB available product price is empty or zero for nm_id %s", requestedNMID)
	}
	return nil
}

func isGenericWBTitle(title string) bool {
	normalized := normalizeWBTitle(title)
	if normalized == "" {
		return false
	}

	patterns := []string{
		"интернет магазин wildberries",
		"широкий ассортимент товаров",
		"скидки каждый день",
		"модный интернет магазин wildberries",
		"wildberries интернет магазин",
	}
	for _, pattern := range patterns {
		if strings.Contains(normalized, pattern) {
			return true
		}
	}
	return false
}

func normalizeWBTitle(title string) string {
	return strings.Join(strings.FieldsFunc(strings.ToLower(strings.TrimSpace(title)), func(r rune) bool {
		return unicode.IsSpace(r) || r == '-' || r == '‐' || r == '‑' || r == '‒' || r == '–' || r == '—' || r == '―'
	}), " ")
}
