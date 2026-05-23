package ozon

type ozonMainProductWidget struct {
	SKU string `json:"sku"`
	URL string `json:"url"`
}

type ozonPageResponse struct {
	WidgetStates map[string]string `json:"widgetStates"`
}

type ozonTileGridWidget struct {
	Items []ozonProductTile `json:"items"`
}

type ozonShelfWidget struct {
	ProductContainer ozonProductContainer `json:"productContainer"`
}

type ozonProductContainer struct {
	Products []ozonProductTile `json:"products"`
}

type ozonProductTile struct {
	ID        string            `json:"id"`
	SKUID     string            `json:"skuId"`
	Alt       string            `json:"alt"`
	Link      string            `json:"link"`
	Action    ozonProductAction `json:"action"`
	Button    ozonProductButton `json:"button"`
	State     []ozonTileState   `json:"state"`
	MainState []ozonTileState   `json:"mainState"`
}

type ozonProductAction struct {
	Link string `json:"link"`
}

type ozonProductButton struct {
	AddToCartButtonWithQuantity ozonAddToCartButtonWithQuantity `json:"addToCartButtonWithQuantity"`
}

type ozonAddToCartButtonWithQuantity struct {
	MaxItems     int `json:"maxItems"`
	CurrentItems int `json:"currentItems"`
}

type ozonTileState struct {
	Type        string          `json:"type"`
	ID          string          `json:"id"`
	TextAtom    ozonTextAtom    `json:"textAtom"`
	PriceV2     ozonPriceV2     `json:"priceV2"`
	LabelList   ozonLabelList   `json:"labelList"`
	LabelListV2 ozonLabelListV2 `json:"labelListV2"`
}

type ozonLabelList struct {
	Items []ozonLabelListItem `json:"items"`
}

type ozonLabelListV2 struct {
	Items []ozonLabelListItem `json:"items"`
}

type ozonLabelListItem struct {
	Title string `json:"title"`
	Text  any    `json:"text"`
}

type ozonTextAtom struct {
	Text string `json:"text"`
}

type ozonPriceV2 struct {
	Price []ozonPriceItem `json:"price"`
}

type ozonPriceItem struct {
	Text      string `json:"text"`
	TextStyle string `json:"textStyle"`
}

type ozonAspectsWidget struct {
	Aspects []ozonAspect `json:"aspects"`
}

type ozonAspect struct {
	Variants []ozonAspectVariant `json:"variants"`
}

type ozonAspectVariant struct {
	SKU          string                `json:"sku"`
	Availability string                `json:"availability"`
	Price        int                   `json:"price"`
	Data         ozonAspectVariantData `json:"data"`
}

type ozonAspectVariantData struct {
	Title string `json:"title"`
	Price string `json:"price"`
}

type CatalogRequest struct {
	Mode  string
	Input string
	Limit int
}

type ozonHTTPError struct {
	StatusCode int
	Body       string
}

type OzonCategoryCandidate struct {
	Title string
	URL   string
}

type ozonFiltersWidget struct {
	Sections []ozonFilterSection `json:"sections"`
}

type ozonFilterSection struct {
	Filters []ozonFilter `json:"filters"`
}

type ozonFilter struct {
	Type           string             `json:"type"`
	Key            string             `json:"key"`
	CategoryFilter ozonCategoryFilter `json:"categoryFilter"`
}

type ozonCategoryFilter struct {
	Title      string                   `json:"title"`
	Categories []ozonCategoryFilterItem `json:"categories"`
}

type ozonCategoryFilterItem struct {
	Title    string `json:"title"`
	Level    int    `json:"level"`
	URLValue string `json:"urlValue"`
}
