package ozon

import (
	"context"
	"time"

	"go_fetcher/internal/models"
	"go_fetcher/internal/observability"
)

func (p *Parser) observeHTTPParserResult(
	ctx context.Context,
	mode string,
	startedAt time.Time,
	err error,
	products []models.Product,
) {
	mode = observability.NormalizeMode(mode)
	result := "success"
	reason := "none"

	if err != nil {
		result = "error"
		reason = observability.NormalizeReason(
			classifyFallbackReason(ctx, err, products),
		)
	} else if !isValidOzonProductList(products) {
		result = "invalid_products"
		reason = "invalid_or_empty_products"
	}

	observability.ParserOperationsTotal.WithLabelValues(
		"ozon",
		mode,
		"http",
		result,
		reason,
	).Inc()

	observability.ParserOperationDurationSeconds.WithLabelValues(
		"ozon",
		mode,
		"http",
		result,
	).Observe(time.Since(startedAt).Seconds())

	if result != "success" {
		observability.MarketplaceFailuresTotal.WithLabelValues(
			"ozon",
			mode+"_http_parser",
			reason,
		).Inc()
	}
}

func (p *Parser) observeBrowserFallbackStarted(
	mode string,
	reason string,
) time.Time {
	mode = observability.NormalizeMode(mode)
	reason = observability.NormalizeReason(reason)

	observability.OzonBrowserFallbackAttemptsTotal.WithLabelValues(
		mode,
		reason,
	).Inc()
	observability.OzonBrowserFallbackInProgress.WithLabelValues(
		mode,
	).Inc()

	return time.Now()
}

func (p *Parser) observeBrowserFallbackSkipped(
	mode string,
	reason string,
) {
	mode = observability.NormalizeMode(mode)
	reason = observability.NormalizeReason(reason)

	observability.OzonBrowserFallbackResultsTotal.WithLabelValues(
		mode,
		"skipped",
		reason,
	).Inc()
}

func (p *Parser) observeBrowserFallbackFinished(
	mode string,
	result string,
	reason string,
	startedAt time.Time,
) {
	mode = observability.NormalizeMode(mode)
	reason = observability.NormalizeReason(reason)

	if result != "success" && result != "failed" {
		result = "unknown"
	}

	observability.OzonBrowserFallbackResultsTotal.WithLabelValues(
		mode,
		result,
		reason,
	).Inc()
	observability.OzonBrowserFallbackDurationSeconds.WithLabelValues(
		mode,
		result,
	).Observe(time.Since(startedAt).Seconds())
	observability.OzonBrowserFallbackInProgress.WithLabelValues(
		mode,
	).Dec()

	observability.ParserOperationsTotal.WithLabelValues(
		"ozon",
		mode,
		"browser",
		result,
		reason,
	).Inc()
	observability.ParserOperationDurationSeconds.WithLabelValues(
		"ozon",
		mode,
		"browser",
		result,
	).Observe(time.Since(startedAt).Seconds())

	if result == "success" {
		observability.OzonBrowserFallbackLastSuccessTimestampSeconds.WithLabelValues(
			mode,
		).SetToCurrentTime()
		return
	}

	observability.MarketplaceFailuresTotal.WithLabelValues(
		"ozon",
		mode+"_browser_fallback",
		reason,
	).Inc()
}
