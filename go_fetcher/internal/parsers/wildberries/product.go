package wildberries

import (
	"context"
	"fmt"
	"go_fetcher/internal/models"
	"log/slog"
)

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
