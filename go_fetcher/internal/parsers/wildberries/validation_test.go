package wildberries

import (
	"strings"
	"testing"
)

func TestValidateWBProductResponse(t *testing.T) {
	valid := wbProduct{ID: 881219291, Name: "Смартфон iPhone 17 Pro 512 ГБ", SalePriceU: 14999000, TotalQuantity: 2}

	tests := []struct {
		name        string
		product     wbProduct
		requested   string
		wantErrPart string
	}{
		{name: "valid", product: valid, requested: "881219291"},
		{name: "different nm id", product: func() wbProduct { p := valid; p.ID = 123; return p }(), requested: "881219291", wantErrPart: "mismatch"},
		{name: "zero price", product: func() wbProduct { p := valid; p.SalePriceU = 0; return p }(), requested: "881219291", wantErrPart: "price"},
		{name: "generic title", product: func() wbProduct {
			p := valid
			p.Name = "Интернет-магазин Wildberries: широкий ассортимент товаров — скидки каждый день!"
			return p
		}(), requested: "881219291", wantErrPart: "generic"},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			products, err := validateWBProductResponse(wbProductsResponse{Products: []wbProduct{test.product}}, test.requested)
			if test.wantErrPart == "" {
				if err != nil {
					t.Fatalf("validate returned error: %v", err)
				}
				if len(products) != 1 || products[0].PriceCents != 14999000 {
					t.Fatalf("unexpected products: %#v", products)
				}
				return
			}
			if err == nil || !strings.Contains(strings.ToLower(err.Error()), test.wantErrPart) {
				t.Fatalf("error = %v, want substring %q", err, test.wantErrPart)
			}
		})
	}
}

func TestIsGenericWBTitleNormalizesCaseWhitespaceAndDashes(t *testing.T) {
	if !isGenericWBTitle("  ИНТЕРНЕТ—МАГАЗИН   Wildberries: скидки каждый день! ") {
		t.Fatal("generic title was not recognized")
	}
}
