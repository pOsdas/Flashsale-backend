package wildberries

import (
	"context"
	"fmt"

	"go_fetcher/internal/models"
)

type Parser struct{}

func NewParser() *Parser {
	return &Parser{}
}

func (p *Parser) ParseProduct(ctx context.Context, productID string) (*models.Product, error) {
	if productID == "" {
		return nil, fmt.Errorf("product id is required")
	}

	product := &models.Product{
		SKU:        "WB-" + productID,
		Title:      "Test Wildberries Product",
		PriceCents: 199900,
		Currency:   "RUB",
		Available:  10,
		IsActive:   true,
	}

	return product, nil
}
