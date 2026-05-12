package models

type Product struct {
	SKU        string
	Title      string
	PriceCents int
	Currency   string
	Available  int
	IsActive   bool
}

type ProductImport struct {
	SKU        string `json:"sku"`
	Title      string `json:"title"`
	PriceCents int    `json:"price_cents"`
	Currency   string `json:"currency"`
	Available  int    `json:"available"`
	IsActive   bool   `json:"is_active"`
}

func (p Product) ToImport() ProductImport {
	return ProductImport{
		SKU:        p.SKU,
		Title:      p.Title,
		PriceCents: p.PriceCents,
		Currency:   p.Currency,
		Available:  p.Available,
		IsActive:   p.IsActive,
	}
}
