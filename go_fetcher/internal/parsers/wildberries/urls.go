package wildberries

import (
	"fmt"
	"net/url"
	"strconv"
	"strings"
)

func buildDetailURL(nmID string) string {
	values := url.Values{}

	values.Set("appType", "1")
	values.Set("curr", "rub")
	values.Set("dest", "123589323")
	values.Set("spp", "30")
	values.Set("hide_vflags", "4294967296")
	values.Set("hide_dtype", "15")
	values.Set("mdg", "110")
	values.Set("lang", "ru")
	values.Set("ab_testing", "false")
	values.Set("nm", strings.TrimSpace(nmID))

	return detailURL + "?" + values.Encode()
}

func buildSearchURL(query string, page int) string {
	values := buildBaseCatalogQuery(page)
	values.Set("mdg", "100")
	values.Set("query", query)

	return catalogURL + "?" + values.Encode()
}

func buildCategoryURL(categoryName string, page int) string {
	categoryQuery := fmt.Sprintf(
		"menu_redirect_subject_v2_9973_corr %s",
		strings.TrimSpace(categoryName),
	)

	values := buildBaseCatalogQuery(page)
	values.Set("mdg", "110")
	values.Set("query", categoryQuery)

	return catalogURL + "?" + values.Encode()
}

func buildBaseCatalogQuery(page int) url.Values {
	values := url.Values{}

	values.Set("ab_testid", "catboost_exp_2")
	values.Set("appType", "1")
	values.Set("curr", "rub")
	values.Set("dest", "123589323")
	values.Set("hide_vflags", "4294967296")
	values.Set("inheritFilters", "false")
	values.Set("lang", "ru")
	values.Set("locale", "ru")
	values.Set("page", strconv.Itoa(page))
	values.Set("resultset", "catalog")
	values.Set("sort", "popular")
	values.Set("spp", "30")
	values.Set("suppressSpellcheck", "false")
	values.Set("uclusters", "2")

	return values
}

func buildProductTitle(product wbProduct) string {
	brand := strings.TrimSpace(product.Brand)
	name := strings.TrimSpace(product.Name)

	switch {
	case brand != "" && name != "":
		return brand + " " + name
	case name != "":
		return name
	case brand != "":
		return brand
	default:
		return strconv.FormatInt(product.ID, 10)
	}
}

func extractPriceCents(product wbProduct) int {
	if product.SalePriceU > 0 {
		return product.SalePriceU
	}

	if product.PriceU > 0 {
		return product.PriceU
	}

	if len(product.Sizes) > 0 && product.Sizes[0].Price.Product > 0 {
		return product.Sizes[0].Price.Product
	}

	if len(product.Sizes) > 0 && product.Sizes[0].Price.Total > 0 {
		return product.Sizes[0].Price.Total
	}

	if len(product.Sizes) > 0 && product.Sizes[0].Price.Basic > 0 {
		return product.Sizes[0].Price.Basic
	}

	return 0
}

func extractOldPriceCents(product wbProduct) int {
	currentPrice := extractPriceCents(product)

	if product.PriceU > 0 && product.PriceU != currentPrice {
		return product.PriceU
	}

	if len(product.Sizes) > 0 && product.Sizes[0].Price.Basic > 0 && product.Sizes[0].Price.Basic != currentPrice {
		return product.Sizes[0].Price.Basic
	}

	return 0
}
