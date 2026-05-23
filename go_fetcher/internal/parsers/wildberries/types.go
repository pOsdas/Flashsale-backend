package wildberries

type wbHTTPError struct {
	StatusCode int
	Body       string
}

type wbProductsResponse struct {
	Products []wbProduct `json:"products"`
}

type wbProduct struct {
	ID            int64    `json:"id"`
	Brand         string   `json:"brand"`
	Name          string   `json:"name"`
	PriceU        int      `json:"priceU"`
	SalePriceU    int      `json:"salePriceU"`
	TotalQuantity int      `json:"totalQuantity"`
	Sizes         []wbSize `json:"sizes"`
}

type wbSize struct {
	Price wbPrice `json:"price"`
}

type wbPrice struct {
	Basic   int `json:"basic"`
	Product int `json:"product"`
	Total   int `json:"total"`
}
