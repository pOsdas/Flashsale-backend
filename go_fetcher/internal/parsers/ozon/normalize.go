package ozon

import (
	"go_fetcher/internal/models"
	"html"
	"strings"
)

func normalizeOzonProductTile(tile ozonProductTile) (models.Product, bool) {
	sku := extractSKUFromTile(tile)
	if sku == "" {
		return models.Product{}, false
	}

	title := extractTitleFromTile(tile)
	if title == "" {
		title = buildTitleFromOzonProductURL(extractLinkFromTile(tile))
	}

	if title == "" {
		return models.Product{}, false
	}

	priceCents := extractPriceCentsFromTile(tile)
	if priceCents <= 0 {
		return models.Product{}, false
	}

	available := extractAvailableFromTile(tile)
	if available <= 0 {
		available = 1
	}

	return models.Product{
		SKU:        sku,
		Title:      title,
		PriceCents: priceCents,
		Currency:   defaultCurrency,
		Available:  available,
		IsActive:   true,
	}, true
}

func extractSKUFromTile(tile ozonProductTile) string {
	sku := strings.TrimSpace(tile.SKUID)
	if sku != "" {
		return sku
	}

	sku = strings.TrimSpace(tile.ID)
	if sku != "" {
		return sku
	}

	link := extractLinkFromTile(tile)
	if link == "" {
		return ""
	}

	return extractProductID(link)
}

func extractLinkFromTile(tile ozonProductTile) string {
	link := strings.TrimSpace(tile.Link)
	if link != "" {
		return link
	}

	link = strings.TrimSpace(tile.Action.Link)
	if link != "" {
		return link
	}

	return ""
}

func extractStatesFromTile(tile ozonProductTile) []ozonTileState {
	states := make([]ozonTileState, 0, len(tile.State)+len(tile.MainState))
	states = append(states, tile.State...)
	states = append(states, tile.MainState...)

	return states
}

func extractTitleFromTile(tile ozonProductTile) string {
	for _, item := range extractStatesFromTile(tile) {
		if item.Type != "textAtom" {
			continue
		}

		if item.ID != "name" {
			continue
		}

		title := strings.TrimSpace(item.TextAtom.Text)
		title = html.UnescapeString(title)
		title = stripHTMLTags(title)

		if title != "" {
			return title
		}
	}

	alt := strings.TrimSpace(tile.Alt)
	alt = html.UnescapeString(alt)
	alt = stripHTMLTags(alt)

	if alt != "" {
		return alt
	}

	return buildTitleFromOzonProductURL(extractLinkFromTile(tile))
}

func extractPriceCentsFromTile(tile ozonProductTile) int {
	for _, item := range extractStatesFromTile(tile) {
		if item.Type != "priceV2" {
			continue
		}

		for _, priceItem := range item.PriceV2.Price {
			if priceItem.TextStyle != "PRICE" {
				continue
			}

			priceRubles := parsePriceRubles(priceItem.Text)
			if priceRubles > 0 {
				return priceRubles * 100
			}
		}

		for _, priceItem := range item.PriceV2.Price {
			priceRubles := parsePriceRubles(priceItem.Text)
			if priceRubles > 0 {
				return priceRubles * 100
			}
		}
	}

	return 0
}

func extractAvailableFromTile(tile ozonProductTile) int {
	for _, item := range extractStatesFromTile(tile) {
		if item.Type == "textAtom" {
			text := strings.ToLower(item.TextAtom.Text)

			if strings.Contains(text, "осталось") {
				quantity := parseFirstInt(text)
				if quantity > 0 {
					return quantity
				}
			}
		}

		for _, labelItem := range item.LabelList.Items {
			text := strings.ToLower(
				labelItem.Title + " " + stringifyOzonValue(labelItem.Text),
			)

			if strings.Contains(text, "осталось") {
				quantity := parseFirstInt(text)
				if quantity > 0 {
					return quantity
				}
			}
		}

		for _, labelItem := range item.LabelListV2.Items {
			text := strings.ToLower(
				labelItem.Title + " " + stringifyOzonValue(labelItem.Text),
			)

			if strings.Contains(text, "осталось") {
				quantity := parseFirstInt(text)
				if quantity > 0 {
					return quantity
				}
			}
		}
	}

	if tile.Button.AddToCartButtonWithQuantity.MaxItems > 0 {
		return tile.Button.AddToCartButtonWithQuantity.MaxItems
	}

	return 0
}
