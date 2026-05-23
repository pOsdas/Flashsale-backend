package ozon

import (
	"encoding/json"
	"regexp"
	"strings"
)

func stringifyOzonValue(value any) string {
	switch typed := value.(type) {
	case string:
		return typed
	case nil:
		return ""
	default:
		rawBytes, err := json.Marshal(typed)
		if err != nil {
			return ""
		}

		return string(rawBytes)
	}
}

func extractProductID(productPath string) string {
	productPath = strings.Trim(productPath, "/")
	parts := strings.Split(productPath, "-")

	if len(parts) == 0 {
		return ""
	}

	lastPart := parts[len(parts)-1]
	lastPart = strings.Trim(lastPart, "/")

	if isDigitsOnly(lastPart) {
		return lastPart
	}

	re := regexp.MustCompile(`\d+`)
	matches := re.FindAllString(productPath, -1)
	if len(matches) == 0 {
		return ""
	}

	return matches[len(matches)-1]
}

func isDigitsOnly(s string) bool {
	for _, r := range s {
		if r < '0' || r > '9' {
			return false
		}
	}

	return true
}

func limitString(value string, maxLength int) string {
	if maxLength <= 0 {
		return ""
	}

	if len(value) <= maxLength {
		return value
	}

	return value[:maxLength] + "...[truncated]"
}
