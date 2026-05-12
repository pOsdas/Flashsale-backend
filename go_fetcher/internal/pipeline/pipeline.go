package pipeline

import (
	"context"
	"fmt"
	"time"

	"go_fetcher/internal/models"
	"go_fetcher/internal/parsers"
	"go_fetcher/internal/sender"
)

type ImportPipeline struct {
	parser parsers.ProductParser
	sender *sender.DjangoSender
	source string
}

func NewImportPipeline(
	parser parsers.ProductParser,
	sender *sender.DjangoSender,
	source string,
) *ImportPipeline {
	return &ImportPipeline{
		parser: parser,
		sender: sender,
		source: source,
	}
}

func (p *ImportPipeline) RunProductImport(
	ctx context.Context,
	productID string,
) (*sender.ImportResponse, error) {
	product, err := p.parser.ParseProduct(ctx, productID)
	if err != nil {
		return nil, fmt.Errorf("failed to parse product: %w", err)
	}

	payload := sender.ImportPayload{
		Source:  p.source,
		BatchID: buildBatchID(p.source, product.SKU),
		Items: []models.ProductImport{
			product.ToImport(),
		},
	}

	response, err := p.sender.SendImport(ctx, payload)
	if err != nil {
		return nil, fmt.Errorf("failed to send import payload: %w", err)
	}

	return response, nil
}

func buildBatchID(source string, sku string) string {
	return fmt.Sprintf(
		"%s-%s-%d",
		source,
		sku,
		time.Now().Unix(),
	)
}
