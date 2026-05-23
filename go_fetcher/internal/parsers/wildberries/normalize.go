package wildberries

import (
	"go_fetcher/internal/models"
	"strconv"
)

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
