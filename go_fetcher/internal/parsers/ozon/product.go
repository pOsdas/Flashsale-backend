package ozon

import (
	"context"
	"fmt"
	"go_fetcher/internal/models"
	"log/slog"
)

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

func (p *Parser) fetchCatalogProducts(ctx context.Context, request CatalogRequest) ([]models.Product, error) {
	if request.Limit <= 0 {
		return nil, fmt.Errorf("limit must be greater than zero")
	}

	collected := make([]models.Product, 0, request.Limit)
	seen := make(map[string]struct{})

	const maxPages = 20

	for page := 1; page <= maxPages && len(collected) < request.Limit; page++ {
		requestURL, err := buildOzonCatalogPageRequestURL(request.Mode, request.Input, page)
		if err != nil {
			return nil, err
		}

		var response ozonPageResponse

		if err := p.doJSONRequest(ctx, requestURL, &response); err != nil {
			return nil, fmt.Errorf("fetch Ozon %s catalog page %d: %w", request.Mode, page, err)
		}

		debugOzonCatalogWidgetStates(
			p.logger,
			request.Mode,
			page,
			requestURL,
			response.WidgetStates,
		)

		products := extractProductsFromWidgetStates(response.WidgetStates)
		products = deduplicateProductsBySKU(products)

		newProductsOnPage := 0

		for _, product := range products {
			if len(collected) >= request.Limit {
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
			newProductsOnPage++
		}

		p.logger.Info(
			"ozon catalog page parsed",
			slog.String("mode", request.Mode),
			slog.Int("page", page),
			slog.Int("received", len(products)),
			slog.Int("new_products", newProductsOnPage),
			slog.Int("collected", len(collected)),
			slog.Int("limit", request.Limit),
		)

		if len(products) == 0 || newProductsOnPage == 0 {
			break
		}
	}

	if len(collected) == 0 {
		return nil, fmt.Errorf("no products extracted from Ozon %s catalog", request.Mode)
	}

	return collected, nil
}
