package models

type Product struct {
	SKU        string
	Title      string
	PriceCents int
	Currency   string
	Available  int
	IsActive   bool
}
