package ozon

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
)

func (p *Parser) ResolveCategories(ctx context.Context, query string, limit int) ([]OzonCategoryCandidate, error) {
	query = strings.TrimSpace(query)
	if query == "" {
		return nil, fmt.Errorf("category query is empty")
	}

	if limit <= 0 {
		limit = 10
	}

	requestURL, err := buildOzonSearchPageRequestURL(query, 1)
	if err != nil {
		return nil, err
	}

	var response ozonPageResponse

	if err := p.doJSONRequest(ctx, requestURL, &response); err != nil {
		return nil, fmt.Errorf("resolve Ozon categories by query %q: %w", query, err)
	}

	categories := extractCategoryCandidatesFromWidgetStates(response.WidgetStates)
	categories = deduplicateCategoryCandidates(categories)

	if len(categories) > limit {
		categories = categories[:limit]
	}

	if len(categories) == 0 {
		return nil, fmt.Errorf("no Ozon categories found for query %q", query)
	}

	return categories, nil
}

func extractCategoryCandidatesFromWidgetStates(widgetStates map[string]string) []OzonCategoryCandidate {
	result := make([]OzonCategoryCandidate, 0)

	for key, rawWidgetState := range widgetStates {
		if !strings.Contains(key, "filtersDesktop") &&
			!strings.Contains(key, "filtersMobile") &&
			!strings.Contains(key, "filters") {
			continue
		}

		var filtersWidget ozonFiltersWidget

		if err := json.Unmarshal([]byte(rawWidgetState), &filtersWidget); err != nil {
			continue
		}

		for _, section := range filtersWidget.Sections {
			for _, filter := range section.Filters {
				if filter.Key != "category" && filter.Type != "categoryFilter" {
					continue
				}

				for _, category := range filter.CategoryFilter.Categories {
					title := strings.TrimSpace(category.Title)
					categoryURL := strings.TrimSpace(category.URLValue)

					if title == "" || categoryURL == "" {
						continue
					}

					if !strings.HasPrefix(categoryURL, "/category/") {
						continue
					}

					result = append(result, OzonCategoryCandidate{
						Title: title,
						URL:   stripOzonURLQuery(categoryURL),
					})
				}
			}
		}
	}

	return result
}

func stripOzonURLQuery(rawURL string) string {
	rawURL = strings.TrimSpace(rawURL)

	queryIndex := strings.Index(rawURL, "?")
	if queryIndex == -1 {
		return rawURL
	}

	return rawURL[:queryIndex]
}

func deduplicateCategoryCandidates(categories []OzonCategoryCandidate) []OzonCategoryCandidate {
	result := make([]OzonCategoryCandidate, 0, len(categories))
	seen := make(map[string]struct{}, len(categories))

	for _, category := range categories {
		if category.URL == "" {
			continue
		}

		if _, exists := seen[category.URL]; exists {
			continue
		}

		seen[category.URL] = struct{}{}
		result = append(result, category)
	}

	return result
}
