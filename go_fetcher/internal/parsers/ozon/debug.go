package ozon

import (
	"fmt"
	"log/slog"
	"strings"
)

func debugOzonWidgetStates(widgetStates map[string]string) {
	fmt.Printf("Ozon widgetStates count: %d\n", len(widgetStates))

	for key, value := range widgetStates {
		lowerKey := strings.ToLower(key)
		lowerValue := strings.ToLower(value)

		if strings.Contains(lowerKey, "price") ||
			strings.Contains(lowerKey, "sku") ||
			strings.Contains(lowerKey, "product") ||
			strings.Contains(lowerKey, "title") ||
			strings.Contains(lowerKey, "heading") ||
			strings.Contains(lowerKey, "order") ||
			strings.Contains(lowerValue, "sku") ||
			strings.Contains(lowerValue, "price") ||
			strings.Contains(lowerValue, "name") ||
			strings.Contains(lowerValue, "title") {
			fmt.Println("========== WIDGET ==========")
			fmt.Println("KEY:", key)

			if len(value) > 1000 {
				fmt.Println("VALUE:", value[:1000])
			} else {
				fmt.Println("VALUE:", value)
			}
		}
	}
}

func debugOzonCatalogWidgetStates(
	logger *slog.Logger,
	mode string,
	page int,
	requestURL string,
	widgetStates map[string]string,
) {
	logger.Info(
		"ozon widgetStates debug",
		slog.String("mode", mode),
		slog.Int("page", page),
		slog.String("request_url", requestURL),
		slog.Int("widget_states_count", len(widgetStates)),
	)

	for key, value := range widgetStates {
		lowerKey := strings.ToLower(key)
		lowerValue := strings.ToLower(value)

		if strings.Contains(lowerKey, "search") ||
			strings.Contains(lowerKey, "catalog") ||
			strings.Contains(lowerKey, "tile") ||
			strings.Contains(lowerKey, "sku") ||
			strings.Contains(lowerKey, "product") ||
			strings.Contains(lowerKey, "container") ||
			strings.Contains(lowerValue, "sku") ||
			strings.Contains(lowerValue, "skuid") ||
			strings.Contains(lowerValue, "price") ||
			strings.Contains(lowerValue, "textAtom") ||
			strings.Contains(lowerValue, "tile") ||
			strings.Contains(lowerValue, "product") {
			preview := value
			if len(preview) > 1000 {
				preview = preview[:1000]
			}

			logger.Info(
				"ozon widgetState candidate",
				slog.String("key", key),
				slog.Int("value_len", len(value)),
				slog.String("value_preview", preview),
			)
		}
	}
}
