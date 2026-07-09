package httpserver

import (
	"net/http"
	"strings"
	"time"

	"go_fetcher/internal/observability"
)

type statusRecorder struct {
	http.ResponseWriter
	statusCode  int
	wroteHeader bool
}

func (r *statusRecorder) WriteHeader(statusCode int) {
	if r.wroteHeader {
		return
	}

	r.statusCode = statusCode
	r.wroteHeader = true
	r.ResponseWriter.WriteHeader(statusCode)
}

func (r *statusRecorder) Write(body []byte) (int, error) {
	if !r.wroteHeader {
		r.WriteHeader(http.StatusOK)
	}

	return r.ResponseWriter.Write(body)
}

func observeHTTPRequests(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		route := normalizeMetricRoute(r.URL.Path)
		method := normalizeMetricMethod(r.Method)
		startedAt := time.Now()

		observability.HTTPRequestsInProgress.WithLabelValues(
			route,
			method,
		).Inc()

		recorder := &statusRecorder{
			ResponseWriter: w,
			statusCode:     http.StatusOK,
		}

		defer func() {
			observability.HTTPRequestsTotal.WithLabelValues(
				route,
				method,
				statusClass(recorder.statusCode),
			).Inc()

			observability.HTTPRequestDurationSeconds.WithLabelValues(
				route,
				method,
			).Observe(time.Since(startedAt).Seconds())

			observability.HTTPRequestsInProgress.WithLabelValues(
				route,
				method,
			).Dec()
		}()

		next.ServeHTTP(recorder, r)
	})
}

func observeProductFetch(
	marketplace string,
	result string,
	errorType string,
	startedAt time.Time,
) {
	marketplace = observability.NormalizeMarketplace(marketplace)
	result = normalizeProductFetchResult(result)
	errorType = observability.NormalizeReason(errorType)

	observability.ProductFetchesTotal.WithLabelValues(
		marketplace,
		result,
		errorType,
	).Inc()

	observability.ProductFetchDurationSeconds.WithLabelValues(
		marketplace,
		result,
	).Observe(time.Since(startedAt).Seconds())

	if result == "fetch_error" || result == "not_found" {
		observability.MarketplaceFailuresTotal.WithLabelValues(
			marketplace,
			"product_fetch",
			errorType,
		).Inc()
	}
}

func observeParserHealthResult(
	marketplace string,
	startedAt time.Time,
	item ParserHealthItem,
) {
	marketplace = observability.NormalizeMarketplace(marketplace)
	status := observability.NormalizeHealthStatus(item.Status)
	errorType := "none"

	if rawErrorType, ok := item.Details["error_type"]; ok {
		if value, ok := rawErrorType.(string); ok {
			errorType = observability.NormalizeReason(value)
		}
	}

	if status == "error" && errorType == "none" {
		errorType = "validation_error"
	}

	observability.ParserHealthChecksTotal.WithLabelValues(
		marketplace,
		status,
		errorType,
	).Inc()

	observability.ParserHealthCheckDurationSeconds.WithLabelValues(
		marketplace,
		status,
	).Observe(time.Since(startedAt).Seconds())

	for _, candidate := range []string{"ok", "warning", "error", "unknown"} {
		value := 0.0
		if candidate == status {
			value = 1
		}

		observability.ParserHealthState.WithLabelValues(
			marketplace,
			candidate,
		).Set(value)
	}

	if status == "error" {
		observability.MarketplaceFailuresTotal.WithLabelValues(
			marketplace,
			"parser_health",
			errorType,
		).Inc()
	}
}

func normalizeMetricRoute(path string) string {
	switch strings.TrimRight(strings.TrimSpace(path), "/") {
	case "", "/health":
		return "/health"
	case "/metrics":
		return "/metrics"
	case "/api/v1/fetch/product":
		return "/api/v1/fetch/product"
	case "/api/v1/parser/health":
		return "/api/v1/parser/health"
	default:
		return "unknown"
	}
}

func normalizeMetricMethod(method string) string {
	switch strings.ToUpper(strings.TrimSpace(method)) {
	case http.MethodGet:
		return http.MethodGet
	case http.MethodPost:
		return http.MethodPost
	default:
		return "OTHER"
	}
}

func statusClass(statusCode int) string {
	switch {
	case statusCode >= 200 && statusCode < 300:
		return "2xx"
	case statusCode >= 300 && statusCode < 400:
		return "3xx"
	case statusCode >= 400 && statusCode < 500:
		return "4xx"
	case statusCode >= 500 && statusCode < 600:
		return "5xx"
	default:
		return "other"
	}
}

func normalizeProductFetchResult(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "success":
		return "success"
	case "method_not_allowed":
		return "method_not_allowed"
	case "unauthorized":
		return "unauthorized"
	case "unsupported_media_type":
		return "unsupported_media_type"
	case "invalid_json":
		return "invalid_json"
	case "validation_error":
		return "validation_error"
	case "not_configured":
		return "not_configured"
	case "fetch_error":
		return "fetch_error"
	case "not_found":
		return "not_found"
	default:
		return "unknown"
	}
}
