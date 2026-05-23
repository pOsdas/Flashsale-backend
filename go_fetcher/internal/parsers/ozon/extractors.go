package ozon

import (
	"encoding/json"
	"fmt"
	"go_fetcher/internal/models"
	"html"
	"strings"
)

func extractProductsFromWidgetStates(widgetStates map[string]string) []models.Product {
	result := make([]models.Product, 0)

	mainProduct, ok := extractMainProductFromWidgetStates(widgetStates)
	if ok {
		result = append(result, mainProduct)
	}

	for key, rawWidgetState := range widgetStates {
		if strings.Contains(key, "tileGrid") {
			products := extractProductsFromTileGridWidget(rawWidgetState)
			result = append(result, products...)
			continue
		}

		var decoded any

		if err := json.Unmarshal([]byte(rawWidgetState), &decoded); err != nil {
			continue
		}

		tiles := findOzonProductTiles(decoded)

		for _, tile := range tiles {
			product, ok := normalizeOzonProductTile(tile)
			if !ok {
				continue
			}

			result = append(result, product)
		}
	}

	return result
}

func extractProductsFromTileGridWidget(rawWidgetState string) []models.Product {
	var grid ozonTileGridWidget

	if err := json.Unmarshal([]byte(rawWidgetState), &grid); err != nil {
		fmt.Println("TILE GRID UNMARSHAL ERROR:", err)
		return nil
	}

	fmt.Println("TILE GRID ITEMS:", len(grid.Items))

	products := make([]models.Product, 0, len(grid.Items))

	for _, tile := range grid.Items {
		//fmt.Println("TILE GRID RAW TILE")
		//fmt.Println("  id:", tile.ID)
		//fmt.Println("  skuId:", tile.SKUID)
		//fmt.Println("  link:", extractLinkFromTile(tile))
		//fmt.Println("  states:", len(tile.State))
		//fmt.Println("  mainStates:", len(tile.MainState))
		//fmt.Println("  title:", extractTitleFromTile(tile))
		//fmt.Println("  priceCents:", extractPriceCentsFromTile(tile))
		//fmt.Println("  available:", extractAvailableFromTile(tile))

		product, ok := normalizeOzonProductTile(tile)
		if !ok {
			fmt.Println("  result: dropped")
			continue
		}

		fmt.Println("  result: accepted")
		products = append(products, product)
	}

	return products
}

func extractMainProductFromWidgetStates(widgetStates map[string]string) (models.Product, bool) {
	mainSKU := ""
	mainURL := ""

	for key, rawWidgetState := range widgetStates {
		if !strings.Contains(key, "webProductMainWidget") {
			continue
		}

		var mainWidget ozonMainProductWidget

		if err := json.Unmarshal([]byte(rawWidgetState), &mainWidget); err != nil {
			continue
		}

		mainSKU = strings.TrimSpace(mainWidget.SKU)
		mainURL = strings.TrimSpace(mainWidget.URL)
		break
	}

	if mainSKU == "" {
		return models.Product{}, false
	}

	if aspectProduct, ok := extractProductFromAspects(widgetStates, mainSKU); ok {
		return aspectProduct, true
	}

	title := buildTitleFromOzonProductURL(mainURL)
	if title == "" {
		title = mainSKU
	}

	return models.Product{
		SKU:        mainSKU,
		Title:      title,
		PriceCents: 0,
		Currency:   defaultCurrency,
		Available:  1,
		IsActive:   true,
	}, true
}

func extractProductFromAspects(widgetStates map[string]string, targetSKU string) (models.Product, bool) {
	for key, rawWidgetState := range widgetStates {
		if !strings.Contains(key, "webAspects") {
			continue
		}

		var aspectsWidget ozonAspectsWidget

		if err := json.Unmarshal([]byte(rawWidgetState), &aspectsWidget); err != nil {
			continue
		}

		for _, aspect := range aspectsWidget.Aspects {
			for _, variant := range aspect.Variants {
				if variant.SKU != targetSKU {
					continue
				}

				title := strings.TrimSpace(variant.Data.Title)
				title = html.UnescapeString(title)
				title = stripHTMLTags(title)

				if title == "" {
					title = targetSKU
				}

				priceCents := 0
				if variant.Price > 0 {
					priceCents = variant.Price * 100
				} else {
					priceRubles := parsePriceRubles(variant.Data.Price)
					priceCents = priceRubles * 100
				}

				available := 0
				if variant.Availability == "inStock" {
					available = 1
				}

				return models.Product{
					SKU:        targetSKU,
					Title:      title,
					PriceCents: priceCents,
					Currency:   defaultCurrency,
					Available:  available,
					IsActive:   true,
				}, true
			}
		}
	}

	return models.Product{}, false
}

func findOzonProductTiles(value any) []ozonProductTile {
	result := make([]ozonProductTile, 0)

	switch typed := value.(type) {
	case map[string]any:
		if looksLikeOzonProductTileMap(typed) {
			rawBytes, err := json.Marshal(typed)
			if err == nil {
				var tile ozonProductTile
				if err := json.Unmarshal(rawBytes, &tile); err == nil {
					sku := extractSKUFromTile(tile)
					if sku != "" {
						result = append(result, tile)
					}
				}
			}
		}

		for _, nestedValue := range typed {
			result = append(result, findOzonProductTiles(nestedValue)...)
		}

	case []any:
		for _, item := range typed {
			result = append(result, findOzonProductTiles(item)...)
		}
	}

	return result
}

func looksLikeOzonProductTileMap(value map[string]any) bool {
	if _, ok := value["skuId"]; ok {
		return true
	}

	if _, ok := value["id"]; !ok {
		return false
	}

	if _, ok := value["mainState"]; ok {
		return true
	}

	if _, ok := value["state"]; ok {
		return true
	}

	if _, ok := value["action"]; ok {
		return true
	}

	return false
}
