package models

type Product struct {
	SKU           string
	Title         string
	SellerName    string
	Brand         string
	PriceCents    int
	OldPriceCents int
	Currency      string
	Available     int
	IsActive      bool
	Rating        float64
	ReviewsCount  int
	ProductPath   string
	URL           string
}

type ProductImport struct {
	SKU           string  `json:"sku"`
	Title         string  `json:"title"`
	SellerName    string  `json:"seller_name"`
	Brand         string  `json:"brand"`
	PriceCents    int     `json:"price_cents"`
	OldPriceCents int     `json:"old_price_cents"`
	Currency      string  `json:"currency"`
	Available     int     `json:"available"`
	IsActive      bool    `json:"is_active"`
	Rating        float64 `json:"rating"`
	ReviewsCount  int     `json:"reviews_count"`
}

func (p Product) ToImport() ProductImport {
	return ProductImport{
		SKU:           p.SKU,
		Title:         p.Title,
		SellerName:    p.SellerName,
		Brand:         p.Brand,
		PriceCents:    p.PriceCents,
		OldPriceCents: p.OldPriceCents,
		Currency:      p.Currency,
		Available:     p.Available,
		IsActive:      p.IsActive,
		Rating:        p.Rating,
		ReviewsCount:  p.ReviewsCount,
	}
}