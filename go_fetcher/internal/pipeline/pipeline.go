package pipeline

import (
	"context"
	"fmt"
	"time"

	"go_fetcher/internal/models"
	"go_fetcher/internal/sender"
)

type ImportResponse = sender.ImportResponse

type ImportPipeline struct {
	sender *sender.DjangoSender
}

func NewImportPipeline(sender *sender.DjangoSender) *ImportPipeline {
	return &ImportPipeline{
		sender: sender,
	}
}

func (p *ImportPipeline) ImportProducts(
	ctx context.Context,
	source string,
	products []models.Product,
) (ImportResponse, error) {
	if source == "" {
		return ImportResponse{}, fmt.Errorf("source is required")
	}

	if len(products) == 0 {
		return ImportResponse{}, fmt.Errorf("products list is empty")
	}

	products = deduplicateProductsBySKU(products)

	if len(products) == 0 {
		return ImportResponse{}, fmt.Errorf("products list is empty after deduplication")
	}

	items := make([]models.ProductImport, 0, len(products))

	for _, product := range products {
		items = append(items, product.ToImport())
	}

	payload := sender.ImportPayload{
		Source:  source,
		BatchID: buildBatchID(source),
		Items:   items,
	}

	response, err := p.sender.ImportProducts(ctx, payload)
	if err != nil {
		return ImportResponse{}, fmt.Errorf("import products to Django: %w", err)
	}

	return response, nil
}

func buildBatchID(source string) string {
	return fmt.Sprintf(
		"%s-%d",
		source,
		time.Now().UTC().UnixNano(),
	)
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
