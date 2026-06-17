package httpserver

type FetchProductRequest struct {
	Marketplace string `json:"marketplace"`
	URL         string `json:"url"`
	ExternalID  string `json:"external_id,omitempty"`
}

type FetchProductResponse struct {
	Status  string      `json:"status"`
	Product *ProductDTO `json:"product,omitempty"`
	Error   string      `json:"error,omitempty"`
}

type ProductDTO struct {
	ExternalID     string  `json:"external_id"`
	Title          string  `json:"title"`
	SellerName     string  `json:"seller_name"`
	Brand          string  `json:"brand"`
	PriceCents     int     `json:"price_cents"`
	OldPriceCents  int     `json:"old_price_cents"`
	Currency       string  `json:"currency"`
	IsAvailable    bool    `json:"is_available"`
	Rating         float64 `json:"rating"`
	ReviewsCount   int     `json:"reviews_count"`
	ProductPath     string  `json:"product_path,omitempty"`
	URL             string  `json:"url,omitempty"`
}