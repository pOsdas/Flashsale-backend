package ozon

import (
	"fmt"
	"html"
	"net/url"
	"regexp"
	"strconv"
	"strings"
)

func buildOzonCatalogPageRequestURL(mode string, input string, page int) (string, error) {
	input = strings.TrimSpace(input)

	if input == "" {
		return "", fmt.Errorf("Ozon catalog input is empty")
	}

	if page <= 0 {
		return "", fmt.Errorf("page must be greater than zero")
	}

	switch mode {
	case "search":
		return buildOzonSearchPageRequestURL(input, page)

	case "category":
		return buildOzonCategoryPageRequestURL(input, page)

	default:
		return "", fmt.Errorf("unsupported Ozon catalog mode: %s", mode)
	}
}

func buildOzonSearchPageRequestURL(query string, page int) (string, error) {
	query = strings.TrimSpace(query)

	if query == "" {
		return "", fmt.Errorf("Ozon search query is empty")
	}

	if strings.HasPrefix(query, ozonPageAPIURL) {
		return query, nil
	}

	if isFullOzonURL(query) {
		parsedURL, err := url.Parse(query)
		if err != nil {
			return "", fmt.Errorf("parse Ozon search URL: %w", err)
		}

		if !strings.HasPrefix(parsedURL.Path, "/search/") {
			return "", fmt.Errorf("Ozon search URL path must start with /search/")
		}

		values := parsedURL.Query()
		values.Set("page", strconv.Itoa(page))
		parsedURL.RawQuery = values.Encode()

		return buildOzonPageAPIURL(parsedURL.RequestURI()), nil
	}

	searchValues := url.Values{}
	searchValues.Set("text", query)
	searchValues.Set("page", strconv.Itoa(page))

	searchPath := "/search/?" + searchValues.Encode()

	return buildOzonPageAPIURL(searchPath), nil
}

func buildOzonCategoryPageRequestURL(categoryInput string, page int) (string, error) {
	categoryInput = strings.TrimSpace(categoryInput)

	if categoryInput == "" {
		return "", fmt.Errorf("Ozon category input is empty")
	}

	if strings.HasPrefix(categoryInput, ozonPageAPIURL) {
		return categoryInput, nil
	}

	if isFullOzonURL(categoryInput) {
		parsedURL, err := url.Parse(categoryInput)
		if err != nil {
			return "", fmt.Errorf("parse Ozon category URL: %w", err)
		}

		if !strings.HasPrefix(parsedURL.Path, "/category/") {
			return "", fmt.Errorf("Ozon category URL path must start with /category/")
		}

		values := parsedURL.Query()
		values.Set("page", strconv.Itoa(page))
		values.Set("layout_page_index", strconv.Itoa(page))
		parsedURL.RawQuery = values.Encode()

		return buildOzonPageAPIURL(parsedURL.RequestURI()), nil
	}

	if strings.HasPrefix(categoryInput, "/category/") {
		parsedURL, err := url.Parse(categoryInput)
		if err != nil {
			return "", fmt.Errorf("parse Ozon category path: %w", err)
		}

		values := parsedURL.Query()
		values.Set("page", strconv.Itoa(page))
		values.Set("layout_page_index", strconv.Itoa(page))
		parsedURL.RawQuery = values.Encode()

		return buildOzonPageAPIURL(parsedURL.RequestURI()), nil
	}

	return "", fmt.Errorf("Ozon category input must be full Ozon category URL or /category/... path")
}

func buildOzonPageAPIURL(pagePath string) string {
	values := url.Values{}
	values.Set("url", pagePath)

	return ozonPageAPIURL + "?" + values.Encode()
}

func buildProductRequestURL(productInput string) (string, string, error) {
	if strings.HasPrefix(productInput, ozonPageAPIURL) {
		parsedURL, err := url.Parse(productInput)
		if err != nil {
			return "", "", fmt.Errorf("parse Ozon API URL: %w", err)
		}

		productPath := parsedURL.Query().Get("url")
		if productPath == "" {
			return "", "", fmt.Errorf("Ozon API URL must contain url query parameter")
		}

		return productInput, productPath, nil
	}

	productPath, err := normalizeProductPath(productInput)
	if err != nil {
		return "", "", err
	}

	values := url.Values{}
	values.Set("url", productPath)

	return ozonPageAPIURL + "?" + values.Encode(), productPath, nil
}

func buildTitleFromOzonProductURL(productURL string) string {
	productURL = strings.TrimSpace(productURL)
	if productURL == "" {
		return ""
	}

	if parsedURL, err := url.Parse(productURL); err == nil {
		productURL = parsedURL.Path
	}

	productURL = strings.Trim(productURL, "/")
	if productURL == "" {
		return ""
	}

	parts := strings.Split(productURL, "/")
	if len(parts) == 0 {
		return ""
	}

	slug := strings.TrimSpace(parts[len(parts)-1])
	if slug == "" {
		return ""
	}

	slugParts := strings.Split(slug, "-")
	if len(slugParts) > 1 && isDigitsOnly(slugParts[len(slugParts)-1]) {
		slugParts = slugParts[:len(slugParts)-1]
	}

	title := strings.Join(slugParts, " ")
	title = strings.TrimSpace(title)

	return title
}

func isFullOzonURL(value string) bool {
	return strings.HasPrefix(value, "https://www.ozon.ru") ||
		strings.HasPrefix(value, "http://www.ozon.ru") ||
		strings.HasPrefix(value, "https://ozon.ru") ||
		strings.HasPrefix(value, "http://ozon.ru")
}

func normalizeProductPath(productInput string) (string, error) {
	if strings.HasPrefix(productInput, "https://www.ozon.ru") ||
		strings.HasPrefix(productInput, "http://www.ozon.ru") ||
		strings.HasPrefix(productInput, "https://ozon.ru") ||
		strings.HasPrefix(productInput, "http://ozon.ru") {
		parsedURL, err := url.Parse(productInput)
		if err != nil {
			return "", fmt.Errorf("parse Ozon product URL: %w", err)
		}

		if !strings.HasPrefix(parsedURL.Path, "/product/") {
			return "", fmt.Errorf("Ozon product URL path must start with /product/")
		}

		return ensureTrailingSlash(parsedURL.Path), nil
	}

	if strings.HasPrefix(productInput, "/product/") {
		return ensureTrailingSlash(productInput), nil
	}

	if strings.Contains(productInput, "-") {
		return ensureTrailingSlash("/product/" + productInput), nil
	}

	return "", fmt.Errorf("product input must be full Ozon product URL, /product/... path, or product slug with id")
}

func ensureTrailingSlash(value string) string {
	if strings.HasSuffix(value, "/") {
		return value
	}

	return value + "/"
}

func parsePriceRubles(rawPrice string) int {
	cleaned := strings.TrimSpace(rawPrice)
	cleaned = html.UnescapeString(cleaned)
	cleaned = strings.ReplaceAll(cleaned, "\u2009", "")
	cleaned = strings.ReplaceAll(cleaned, "\u00a0", "")
	cleaned = strings.ReplaceAll(cleaned, " ", "")
	cleaned = strings.ReplaceAll(cleaned, "₽", "")
	cleaned = strings.ReplaceAll(cleaned, "р.", "")
	cleaned = strings.ReplaceAll(cleaned, "руб.", "")
	cleaned = strings.ReplaceAll(cleaned, ",", ".")
	cleaned = strings.TrimSpace(cleaned)

	if cleaned == "" {
		return 0
	}

	if strings.Contains(cleaned, ".") {
		parts := strings.Split(cleaned, ".")
		cleaned = parts[0]
	}

	value, err := strconv.Atoi(cleaned)
	if err != nil {
		return 0
	}

	return value
}

func parseFirstInt(rawText string) int {
	re := regexp.MustCompile(`\d+`)
	match := re.FindString(rawText)
	if match == "" {
		return 0
	}

	value, err := strconv.Atoi(match)
	if err != nil {
		return 0
	}

	return value
}

func stripHTMLTags(value string) string {
	re := regexp.MustCompile(`<[^>]*>`)
	return strings.TrimSpace(re.ReplaceAllString(value, ""))
}
