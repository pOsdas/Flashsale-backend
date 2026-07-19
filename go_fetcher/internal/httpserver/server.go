package httpserver

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"go_fetcher/internal/models"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus/promhttp"
)

type ProductFetcher func(ctx context.Context, req FetchProductRequest) (*ProductDTO, error)

type ProductSearchParser interface {
	SearchProducts(ctx context.Context, query string, limit int) ([]models.Product, error)
	ParseProduct(ctx context.Context, productInput string) ([]models.Product, error)
}

type Server struct {
	addr               string
	apiKey             string
	logger             *slog.Logger
	wbFetcher          ProductFetcher
	ozonFetcher        ProductFetcher
	wbParser           ProductSearchParser
	ozonParser         ProductSearchParser
	parserHealthConfig ParserHealthConfig
}

type ParserHealthConfig struct {
	MarketplaceTimeout time.Duration
	HandlerTimeout     time.Duration
}

const (
	defaultParserHealthMarketplaceTimeout = 90 * time.Second
	defaultParserHealthHandlerTimeoutGap  = 10 * time.Second
)

type ParserHealthResponse struct {
	Status string                      `json:"status"`
	Checks map[string]ParserHealthItem `json:"checks"`
}

type ParserHealthItem struct {
	Status  string                 `json:"status"`
	Details map[string]interface{} `json:"details"`
}

type ParserErrorDetails struct {
	ErrorType  string
	StatusCode int
	Message    string
	Error      string
	Details    map[string]interface{}
}

type parserErrorDetailsProvider interface {
	ParserDetails() map[string]interface{}
}

func NewServer(
	addr string,
	apiKey string,
	logger *slog.Logger,
	wbFetcher ProductFetcher,
	ozonFetcher ProductFetcher,
	wbParser ProductSearchParser,
	ozonParser ProductSearchParser,
	parserHealthConfig ParserHealthConfig,
) *Server {
	if parserHealthConfig.MarketplaceTimeout <= 0 {
		parserHealthConfig.MarketplaceTimeout = defaultParserHealthMarketplaceTimeout
	}
	if parserHealthConfig.HandlerTimeout <= parserHealthConfig.MarketplaceTimeout {
		parserHealthConfig.HandlerTimeout = parserHealthConfig.MarketplaceTimeout + defaultParserHealthHandlerTimeoutGap
	}

	return &Server{
		addr:               addr,
		apiKey:             apiKey,
		logger:             logger,
		wbFetcher:          wbFetcher,
		ozonFetcher:        ozonFetcher,
		wbParser:           wbParser,
		ozonParser:         ozonParser,
		parserHealthConfig: parserHealthConfig,
	}
}

func (s *Server) Run(ctx context.Context) error {
	mux := http.NewServeMux()

	mux.HandleFunc("/health", s.handleHealth)
	mux.HandleFunc("/health/", s.handleHealth)
	mux.HandleFunc("/api/v1/fetch/product/", s.handleFetchProduct)
	mux.HandleFunc("/api/v1/parser/health", s.handleParserHealth)
	mux.HandleFunc("/api/v1/parser/health/", s.handleParserHealth)
	mux.Handle("/metrics", promhttp.Handler())

	writeTimeout := 75 * time.Second
	if minimumWriteTimeout := s.parserHealthConfig.HandlerTimeout + 5*time.Second; minimumWriteTimeout > writeTimeout {
		writeTimeout = minimumWriteTimeout
	}

	httpServer := &http.Server{
		Addr:              s.addr,
		Handler:           observeHTTPRequests(mux),
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       20 * time.Second,
		WriteTimeout:      writeTimeout,
		IdleTimeout:       60 * time.Second,
	}

	errCh := make(chan error, 1)

	go func() {
		s.logger.Info("go_fetcher http server started", "addr", s.addr)

		s.logger.Info(
			"GO_FETCHER_HTTP_SERVER_LISTENING",
			slog.String("addr", s.addr),
		)

		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			errCh <- err
			return
		}

		errCh <- nil
	}()

	select {
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		s.logger.Info("go_fetcher http server shutting down")

		if err := httpServer.Shutdown(shutdownCtx); err != nil {
			return err
		}

		return nil

	case err := <-errCh:
		return err
	}
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeHealthJSON(
			w,
			http.StatusMethodNotAllowed,
			map[string]interface{}{
				"status": "error",
				"error":  "method_not_allowed",
			},
		)
		return
	}

	writeHealthJSON(
		w,
		http.StatusOK,
		map[string]interface{}{
			"status":  "ok",
			"service": "go_fetcher",
		},
	)
}

func (s *Server) handleParserHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeHealthJSON(
			w,
			http.StatusMethodNotAllowed,
			ParserHealthResponse{
				Status: "unhealthy",
				Checks: map[string]ParserHealthItem{
					"go_fetcher": {
						Status: "error",
						Details: map[string]interface{}{
							"error": "method_not_allowed",
						},
					},
				},
			},
		)
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), s.parserHealthConfig.HandlerTimeout)
	defer cancel()

	checks := map[string]ParserHealthItem{
		"go_fetcher": {
			Status: "ok",
			Details: map[string]interface{}{
				"service":  "go_fetcher",
				"endpoint": "/api/v1/parser/health",
			},
		},
	}

	type marketplaceHealthResult struct {
		marketplace string
		item        ParserHealthItem
	}

	resultCh := make(chan marketplaceHealthResult, 2)
	parsers := []struct {
		marketplace string
		parser      ProductSearchParser
	}{
		{marketplace: "wb", parser: s.wbParser},
		{marketplace: "ozon", parser: s.ozonParser},
	}

	pending := map[string]struct{}{"wb": {}, "ozon": {}}
	for _, parserCheck := range parsers {
		parserCheck := parserCheck
		go func() {
			item := s.runMarketplaceHealthCheck(ctx, parserCheck.marketplace, "iphone", parserCheck.parser)
			resultCh <- marketplaceHealthResult{marketplace: parserCheck.marketplace, item: item}
		}()
	}

	for len(pending) > 0 {
		select {
		case result := <-resultCh:
			checks[result.marketplace] = result.item
			delete(pending, result.marketplace)
		case <-ctx.Done():
			for marketplace := range pending {
				checks[marketplace] = parserHealthContextError(marketplace, ctx.Err())
			}
			pending = nil
		}
	}

	response := ParserHealthResponse{
		Status: s.buildParserHealthStatus(checks),
		Checks: checks,
	}

	statusCode := http.StatusOK

	if response.Status == "unhealthy" {
		statusCode = http.StatusServiceUnavailable
	}

	writeHealthJSON(w, statusCode, response)
}

func (s *Server) runMarketplaceHealthCheck(
	parentCtx context.Context,
	marketplace string,
	query string,
	parser ProductSearchParser,
) ParserHealthItem {
	startedAt := time.Now()
	deadline, hasDeadline := parentCtx.Deadline()
	parentDeadline := "none"
	timeRemaining := time.Duration(0)
	if hasDeadline {
		parentDeadline = deadline.Format(time.RFC3339Nano)
		timeRemaining = time.Until(deadline)
	}

	s.logger.Info(
		"parser marketplace health check started",
		slog.String("marketplace", marketplace),
		slog.Duration("health_timeout", s.parserHealthConfig.MarketplaceTimeout),
		slog.String("parent_deadline", parentDeadline),
		slog.Duration("time_remaining", timeRemaining),
	)

	checkCtx, cancel := context.WithTimeout(parentCtx, s.parserHealthConfig.MarketplaceTimeout)
	defer cancel()
	result := s.checkMarketplaceParser(checkCtx, marketplace, query, parser)

	s.logger.Info(
		"parser marketplace health check finished",
		slog.String("marketplace", marketplace),
		slog.Duration("health_timeout", s.parserHealthConfig.MarketplaceTimeout),
		slog.String("parent_deadline", parentDeadline),
		slog.Duration("time_remaining", contextTimeRemaining(parentCtx)),
		slog.Duration("duration", time.Since(startedAt)),
		slog.String("result_status", result.Status),
	)

	return result
}

func contextTimeRemaining(ctx context.Context) time.Duration {
	deadline, ok := ctx.Deadline()
	if !ok {
		return 0
	}
	remaining := time.Until(deadline)
	if remaining < 0 {
		return 0
	}
	return remaining
}

func parserHealthContextError(marketplace string, err error) ParserHealthItem {
	errorText := "parser health context ended"
	if err != nil {
		errorText = err.Error()
	}
	return ParserHealthItem{
		Status: "error",
		Details: map[string]interface{}{
			"marketplace": marketplace,
			"scenario":    "search_then_product_parse",
			"error_type":  "network_timeout",
			"message":     "Marketplace health check timed out or was canceled",
			"error":       errorText,
		},
	}
}

func (s *Server) checkMarketplaceParser(
	ctx context.Context,
	marketplace string,
	query string,
	parser ProductSearchParser,
) (result ParserHealthItem) {
	startedAt := time.Now()

	defer func() {
		observeParserHealthResult(
			marketplace,
			startedAt,
			result,
		)
	}()
	if parser == nil {
		return ParserHealthItem{
			Status: "error",
			Details: map[string]interface{}{
				"marketplace": marketplace,
				"error":       "parser is not configured",
			},
		}
	}

	searchProducts, searchErr := parser.SearchProducts(ctx, query, 5)
	if searchErr != nil {
		s.logger.Warn(
			"parser health search failed",
			slog.String("marketplace", marketplace),
			slog.String("query", query),
			slog.String("error", searchErr.Error()),
		)

		classifiedError := classifyParserError(searchErr)

		details := map[string]interface{}{
			"marketplace": marketplace,
			"scenario":    "search_then_product_parse",
			"query":       query,
			"step":        "search",
			"error_type":  classifiedError.ErrorType,
			"message":     classifiedError.Message,
			"error":       classifiedError.Error,
			"duration_ms": time.Since(startedAt).Milliseconds(),
		}

		if classifiedError.StatusCode > 0 {
			details["status_code"] = classifiedError.StatusCode
		}

		addParserErrorDetails(details, classifiedError)

		return ParserHealthItem{
			Status:  "error",
			Details: details,
		}
	}

	product, ok := findFirstValidProduct(searchProducts)
	if !ok {
		return ParserHealthItem{
			Status: "error",
			Details: map[string]interface{}{
				"marketplace":    marketplace,
				"scenario":       "search_then_product_parse",
				"query":          query,
				"step":           "search_validation",
				"products_found": len(searchProducts),
				"error":          "no valid product with sku and title found",
				"duration_ms":    time.Since(startedAt).Milliseconds(),
			},
		}
	}

	parseInput := buildProductParseInput(marketplace, product)
	if parseInput == "" {
		return ParserHealthItem{
			Status: "warning",
			Details: map[string]interface{}{
				"marketplace":        marketplace,
				"scenario":           "search_then_product_parse",
				"query":              query,
				"step":               "product_parse",
				"search_products":    len(searchProducts),
				"selected_sku":       product.SKU,
				"selected_title":     product.Title,
				"selected_price":     product.PriceCents,
				"selected_available": product.Available,
				"reason":             "search works, but product URL/path is missing, product parse was skipped",
				"duration_ms":        time.Since(startedAt).Milliseconds(),
			},
		}
	}

	parsedProducts, parseErr := parser.ParseProduct(ctx, parseInput)
	if parseErr != nil {
		s.logger.Warn(
			"parser health product parse failed",
			slog.String("marketplace", marketplace),
			slog.String("query", query),
			slog.String("product_input", parseInput),
			slog.String("sku", product.SKU),
			slog.String("title", product.Title),
			slog.String("error", parseErr.Error()),
		)

		classifiedError := classifyParserError(parseErr)

		details := map[string]interface{}{
			"marketplace":            marketplace,
			"scenario":               "search_then_product_parse",
			"query":                  query,
			"step":                   "product_parse",
			"search_products":        len(searchProducts),
			"selected_sku":           product.SKU,
			"selected_title":         product.Title,
			"selected_price":         product.PriceCents,
			"selected_available":     product.Available,
			"selected_product_input": parseInput,
			"error_type":             classifiedError.ErrorType,
			"message":                classifiedError.Message,
			"error":                  classifiedError.Error,
			"duration_ms":            time.Since(startedAt).Milliseconds(),
		}

		if classifiedError.StatusCode > 0 {
			details["status_code"] = classifiedError.StatusCode
		}

		addParserErrorDetails(details, classifiedError)

		return ParserHealthItem{
			Status:  "error",
			Details: details,
		}
	}

	parsedProduct, ok := findFirstValidProduct(parsedProducts)
	if !ok {
		return ParserHealthItem{
			Status: "error",
			Details: map[string]interface{}{
				"marketplace":            marketplace,
				"scenario":               "search_then_product_parse",
				"query":                  query,
				"step":                   "product_validation",
				"search_products":        len(searchProducts),
				"parsed_products":        len(parsedProducts),
				"selected_sku":           product.SKU,
				"selected_title":         product.Title,
				"selected_product_input": parseInput,
				"error":                  "product parser returned no valid product with sku and title",
				"duration_ms":            time.Since(startedAt).Milliseconds(),
			},
		}
	}

	if marketplace == "wb" {
		if parsedProduct.SKU != product.SKU {
			return ParserHealthItem{
				Status: "error",
				Details: map[string]interface{}{
					"marketplace":  marketplace,
					"scenario":     "search_then_product_parse",
					"step":         "product_validation",
					"selected_sku": product.SKU,
					"parsed_sku":   parsedProduct.SKU,
					"error":        "product parser returned a different WB nm_id",
					"duration_ms":  time.Since(startedAt).Milliseconds(),
				},
			}
		}
		if isGenericMarketplaceTitle(parsedProduct.Title) {
			return ParserHealthItem{
				Status: "error",
				Details: map[string]interface{}{
					"marketplace":  marketplace,
					"scenario":     "search_then_product_parse",
					"step":         "product_validation",
					"selected_sku": product.SKU,
					"parsed_sku":   parsedProduct.SKU,
					"parsed_title": parsedProduct.Title,
					"error":        "product parser returned a generic Wildberries page title",
					"duration_ms":  time.Since(startedAt).Milliseconds(),
				},
			}
		}
		if (product.Available > 0 || product.PriceCents > 0) && parsedProduct.PriceCents <= 0 {
			return ParserHealthItem{
				Status: "error",
				Details: map[string]interface{}{
					"marketplace":  marketplace,
					"scenario":     "search_then_product_parse",
					"step":         "product_validation",
					"selected_sku": product.SKU,
					"parsed_sku":   parsedProduct.SKU,
					"parsed_title": parsedProduct.Title,
					"parsed_price": parsedProduct.PriceCents,
					"error":        "available WB product parser returned an empty or zero price",
					"duration_ms":  time.Since(startedAt).Milliseconds(),
				},
			}
		}
	}

	checkStatus := "ok"

	details := map[string]interface{}{
		"marketplace":            marketplace,
		"scenario":               "search_then_product_parse",
		"query":                  query,
		"step":                   "completed",
		"search_products":        len(searchProducts),
		"parsed_products":        len(parsedProducts),
		"selected_sku":           product.SKU,
		"selected_title":         product.Title,
		"selected_price":         product.PriceCents,
		"selected_available":     product.Available,
		"selected_product_input": parseInput,
		"parsed_sku":             parsedProduct.SKU,
		"parsed_title":           parsedProduct.Title,
		"parsed_price":           parsedProduct.PriceCents,
		"parsed_available":       parsedProduct.Available,
		"external_id_found":      parsedProduct.SKU != "",
		"title_found":            parsedProduct.Title != "",
		"price_found":            parsedProduct.PriceCents > 0,
		"availability_found":     parsedProduct.Available >= 0,
		"duration_ms":            time.Since(startedAt).Milliseconds(),
	}

	if parsedProduct.PriceCents <= 0 {
		checkStatus = "warning"
		details["warning"] = "product parsed, but price is empty or zero"
	}

	return ParserHealthItem{
		Status:  checkStatus,
		Details: details,
	}
}

func (s *Server) buildParserHealthStatus(checks map[string]ParserHealthItem) string {
	hasError := false
	hasWarning := false

	for _, check := range checks {
		switch check.Status {
		case "error":
			hasError = true
		case "warning":
			hasWarning = true
		}
	}

	if hasError {
		return "degraded"
	}

	if hasWarning {
		return "degraded"
	}

	return "healthy"
}

func findFirstValidProduct(products []models.Product) (models.Product, bool) {
	for _, product := range products {
		if strings.TrimSpace(product.SKU) == "" {
			continue
		}

		if strings.TrimSpace(product.Title) == "" {
			continue
		}

		return product, true
	}

	return models.Product{}, false
}

func isGenericMarketplaceTitle(title string) bool {
	normalized := strings.ToLower(strings.TrimSpace(title))
	replacer := strings.NewReplacer("-", " ", "‐", " ", "‑", " ", "‒", " ", "–", " ", "—", " ", "―", " ")
	normalized = strings.Join(strings.Fields(replacer.Replace(normalized)), " ")

	patterns := []string{
		"интернет магазин wildberries",
		"широкий ассортимент товаров",
		"скидки каждый день",
		"модный интернет магазин wildberries",
		"wildberries интернет магазин",
	}
	for _, pattern := range patterns {
		if strings.Contains(normalized, pattern) {
			return true
		}
	}
	return false
}

func buildProductParseInput(marketplace string, product models.Product) string {
	switch marketplace {
	case "ozon":
		if strings.TrimSpace(product.ProductPath) != "" {
			return strings.TrimSpace(product.ProductPath)
		}

		if strings.TrimSpace(product.URL) != "" {
			return strings.TrimSpace(product.URL)
		}

		return ""

	case "wb":
		if strings.TrimSpace(product.SKU) != "" {
			return strings.TrimSpace(product.SKU)
		}

		if strings.TrimSpace(product.URL) != "" {
			return strings.TrimSpace(product.URL)
		}

		if strings.TrimSpace(product.ProductPath) != "" {
			return strings.TrimSpace(product.ProductPath)
		}

		return ""

	default:
		if strings.TrimSpace(product.URL) != "" {
			return strings.TrimSpace(product.URL)
		}

		if strings.TrimSpace(product.ProductPath) != "" {
			return strings.TrimSpace(product.ProductPath)
		}

		if strings.TrimSpace(product.SKU) != "" {
			return strings.TrimSpace(product.SKU)
		}

		return ""
	}
}

func truncateString(value string, maxLen int) string {
	value = strings.TrimSpace(value)

	if maxLen <= 0 {
		return ""
	}

	if len(value) <= maxLen {
		return value
	}

	return value[:maxLen] + "...[truncated]"
}

func classifyParserError(err error) ParserErrorDetails {
	if err == nil {
		return ParserErrorDetails{
			ErrorType: "unknown_error",
			Message:   "unknown parser error",
			Error:     "",
		}
	}

	errorText := strings.TrimSpace(err.Error())
	lowerErrorText := strings.ToLower(errorText)
	extraDetails := extractParserErrorDetails(err)

	if finalSource, _ := extraDetails["final_error_source"].(string); finalSource == "browser_fallback" {
		fallbackType, _ := extraDetails["browser_fallback_error_type"].(string)
		switch fallbackType {
		case "parser_response_invalid":
			return ParserErrorDetails{
				ErrorType: "parser_response_invalid",
				Message:   "Browser fallback received HTTP 200 but marketplace data failed validation",
				Error:     truncateString(errorText, 500),
				Details:   extraDetails,
			}
		case "browser_fallback_timeout":
			return ParserErrorDetails{
				ErrorType: "browser_fallback_timeout",
				Message:   "Browser fallback timed out while waiting for marketplace data",
				Error:     truncateString(errorText, 500),
				Details:   extraDetails,
			}
		case "blocked_by_antibot":
			statusCode := http.StatusForbidden
			if strings.Contains(lowerErrorText, "498") {
				statusCode = 498
			}
			return ParserErrorDetails{
				ErrorType:  "blocked_by_antibot",
				StatusCode: statusCode,
				Message:    "Browser fallback was also rejected by marketplace antibot",
				Error:      stripErrorBody(errorText),
				Details:    extraDetails,
			}
		case "browser_fallback_error":
			return ParserErrorDetails{
				ErrorType: "browser_fallback_error",
				Message:   "Browser fallback failed after the direct HTTP parser",
				Error:     truncateString(errorText, 500),
				Details:   extraDetails,
			}
		}
	}

	if strings.Contains(lowerErrorText, "temporarily blocked") &&
		strings.Contains(lowerErrorText, "rate_limited") {
		return ParserErrorDetails{
			ErrorType: "rate_limited",
			Message:   "Marketplace is temporarily paused after rate limit response",
			Error:     truncateString(errorText, 500),
			Details:   extraDetails,
		}
	}

	if strings.Contains(lowerErrorText, "temporarily blocked") &&
		strings.Contains(lowerErrorText, "blocked_by_antibot") {
		return ParserErrorDetails{
			ErrorType: "blocked_by_antibot",
			Message:   "Marketplace is temporarily paused after antibot response",
			Error:     truncateString(errorText, 500),
			Details:   extraDetails,
		}
	}

	if strings.Contains(lowerErrorText, "status code: 498") ||
		strings.Contains(lowerErrorText, "status code 498") ||
		strings.Contains(lowerErrorText, "antibot") ||
		strings.Contains(lowerErrorText, "__wbaas/challenges/antibot") ||
		strings.Contains(lowerErrorText, "почти готово") {
		return ParserErrorDetails{
			ErrorType:  "blocked_by_antibot",
			StatusCode: 498,
			Message:    "Marketplace returned antibot challenge",
			Error:      stripErrorBody(errorText),
			Details:    extraDetails,
		}
	}

	if strings.Contains(lowerErrorText, "status code: 429") ||
		strings.Contains(lowerErrorText, "status code 429") {
		return ParserErrorDetails{
			ErrorType:  "rate_limited",
			StatusCode: 429,
			Message:    "Marketplace rate limit exceeded",
			Error:      stripErrorBody(errorText),
			Details:    extraDetails,
		}
	}

	if strings.Contains(lowerErrorText, "status code: 403") ||
		strings.Contains(lowerErrorText, "status code 403") {
		return ParserErrorDetails{
			ErrorType:  "blocked_by_antibot",
			StatusCode: 403,
			Message:    "Marketplace rejected request with forbidden or antibot response",
			Error:      stripErrorBody(errorText),
			Details:    extraDetails,
		}
	}

	if strings.Contains(lowerErrorText, "timeout") ||
		strings.Contains(lowerErrorText, "deadline exceeded") ||
		strings.Contains(lowerErrorText, "context canceled") {
		return ParserErrorDetails{
			ErrorType: "network_timeout",
			Message:   "Marketplace request timed out",
			Error:     truncateString(errorText, 500),
			Details:   extraDetails,
		}
	}

	if strings.Contains(lowerErrorText, "no such host") ||
		strings.Contains(lowerErrorText, "connection refused") ||
		strings.Contains(lowerErrorText, "connection reset") {
		return ParserErrorDetails{
			ErrorType: "network_error",
			Message:   "Marketplace network request failed",
			Error:     truncateString(errorText, 500),
			Details:   extraDetails,
		}
	}

	return ParserErrorDetails{
		ErrorType: "parser_error",
		Message:   "Parser request failed",
		Error:     truncateString(errorText, 500),
		Details:   extraDetails,
	}
}

func extractParserErrorDetails(err error) map[string]interface{} {
	var detailsProvider parserErrorDetailsProvider
	if !errors.As(err, &detailsProvider) {
		return nil
	}

	return detailsProvider.ParserDetails()
}

func addParserErrorDetails(details map[string]interface{}, classifiedError ParserErrorDetails) {
	for key, value := range classifiedError.Details {
		details[key] = value
	}
}

func stripErrorBody(errorText string) string {
	errorText = strings.TrimSpace(errorText)

	bodyMarkers := []string{
		", body:",
		" body:",
		", response body:",
		" response body:",
	}

	for _, marker := range bodyMarkers {
		index := strings.Index(strings.ToLower(errorText), strings.ToLower(marker))
		if index >= 0 {
			return truncateString(strings.TrimSpace(errorText[:index]), 500)
		}
	}

	return truncateString(errorText, 500)
}

func writeHealthJSON(w http.ResponseWriter, statusCode int, payload interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)

	if err := json.NewEncoder(w).Encode(payload); err != nil {
		_, _ = w.Write([]byte(
			fmt.Sprintf(`{"status":"error","error":"failed_to_encode_json","details":%q}`, err.Error()),
		))
	}
}
