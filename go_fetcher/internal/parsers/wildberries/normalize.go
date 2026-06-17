package wildberries

import (
	"go_fetcher/internal/models"
	"strconv"
	"strings"
)

func normalizeWBProducts(products []wbProduct) []models.Product {
	result := make([]models.Product, 0, len(products))

	for _, product := range products {
		normalized := models.Product{
			SKU:           strconv.FormatInt(product.ID, 10),
			Title:         buildProductTitle(product),
			SellerName:    strings.TrimSpace(product.Supplier),
			Brand:         strings.TrimSpace(product.Brand),
			PriceCents:    extractPriceCents(product),
			OldPriceCents: extractOldPriceCents(product),
			Currency:      defaultCurrency,
			Available:     product.TotalQuantity,
			IsActive:      product.TotalQuantity > 0,
			Rating:        product.ReviewRating,
			ReviewsCount:  product.Feedbacks,
		}

		if normalized.SKU == "" || normalized.Title == "" {
			continue
		}

		result = append(result, normalized)
	}

	return result
}
