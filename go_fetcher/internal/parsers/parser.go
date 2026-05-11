package parsers

import (
	"context"

	"go_fetcher/internal/models"
)

type ProductParser interface {
	ParseProduct(ctx context.Context, productID string) (*models.Product, error)
}
