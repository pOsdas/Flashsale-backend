package wildberries

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const wbBrowserFetchPath = "/api/v1/fetch"

type BrowserClient struct {
	client   *http.Client
	endpoint string
	logger   *slog.Logger
	timeout  time.Duration
}

type wbBrowserFallbackError struct {
	Kind string
	Err  error
}

func (e *wbBrowserFallbackError) Error() string { return e.Err.Error() }
func (e *wbBrowserFallbackError) Unwrap() error { return e.Err }

type wbBrowserFetchResponse struct {
	StatusCode    int             `json:"status_code"`
	Body          json.RawMessage `json:"body"`
	Error         string          `json:"error"`
	RequestedURL  string          `json:"requested_url"`
	FinalURL      string          `json:"final_url"`
	ContentType   string          `json:"content_type"`
	ResponseSize  int             `json:"response_size"`
	DocumentTitle string          `json:"document_title"`
	ResponseKind  string          `json:"response_kind"`
	RequestedNMID string          `json:"requested_nm_id"`
	ParsedNMID    string          `json:"parsed_nm_id"`
	JSONDecodeOK  bool            `json:"json_decode_success"`
	Resultset     string          `json:"resultset"`
	ProductsCount int             `json:"products_count"`
}

func NewBrowserClient(enabled bool, rawURL string, timeout time.Duration, logger *slog.Logger) *BrowserClient {
	if !enabled || strings.TrimSpace(rawURL) == "" {
		return nil
	}

	if timeout <= 0 {
		timeout = defaultWBBrowserFetcherTimeout
	}
	if logger == nil {
		logger = slog.Default()
	}

	return &BrowserClient{
		client:   &http.Client{Timeout: timeout},
		endpoint: strings.TrimRight(strings.TrimSpace(rawURL), "/"),
		logger:   logger,
		timeout:  timeout,
	}
}

func (c *BrowserClient) Enabled() bool {
	return c != nil && c.client != nil && c.endpoint != ""
}

func (c *BrowserClient) FetchJSON(ctx context.Context, requestURL string, target any) error {
	if !c.Enabled() {
		return fmt.Errorf("WB browser fetcher is not configured")
	}

	requestTimeout := c.timeout
	if deadline, ok := ctx.Deadline(); ok {
		if remaining := time.Until(deadline); remaining > 0 && (requestTimeout <= 0 || remaining < requestTimeout) {
			requestTimeout = remaining
		}
	}
	requestTimeoutMS := requestTimeout.Milliseconds()
	if requestTimeoutMS <= 0 {
		requestTimeoutMS = defaultWBBrowserFetcherTimeout.Milliseconds()
	}

	payload, err := json.Marshal(map[string]any{
		"url":                requestURL,
		"request_timeout_ms": requestTimeoutMS,
	})
	if err != nil {
		return fmt.Errorf("encode browser fetcher request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.endpoint+wbBrowserFetchPath, bytes.NewReader(payload))
	if err != nil {
		return fmt.Errorf("create browser fetcher request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	resp, err := c.client.Do(req)
	if err != nil {
		return newWBBrowserFallbackError("", fmt.Errorf("execute browser fetcher request: %w", err))
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("read browser fetcher response: %w", err)
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		var errorResponse struct {
			Error     string `json:"error"`
			ErrorType string `json:"error_type"`
		}
		_ = json.Unmarshal(body, &errorResponse)
		message := strings.TrimSpace(errorResponse.Error)
		if message == "" {
			message = truncateWBBodyPreview(string(body))
		}
		return newWBBrowserFallbackError(
			errorResponse.ErrorType,
			fmt.Errorf("browser fetcher status %d: %s", resp.StatusCode, message),
		)
	}

	var result wbBrowserFetchResponse
	if err := json.Unmarshal(body, &result); err != nil {
		return newWBBrowserFallbackError("browser_fallback_error", fmt.Errorf("decode browser fetcher response: %w", err))
	}
	if result.Error != "" {
		return newWBBrowserFallbackError("", fmt.Errorf("browser fetcher error: %s", result.Error))
	}
	if result.StatusCode < 200 || result.StatusCode >= 300 {
		kind := "browser_fallback_error"
		if result.StatusCode == http.StatusForbidden || result.StatusCode == 498 {
			kind = "blocked_by_antibot"
		}
		return newWBBrowserFallbackError(kind, fmt.Errorf("browser upstream status %d: %s", result.StatusCode, truncateWBBodyPreview(string(result.Body))))
	}

	c.logger.Info(
		"wildberries browser fallback response",
		slog.String("requested_url", requestURL),
		slog.String("final_url", result.FinalURL),
		slog.Int("status", result.StatusCode),
		slog.String("content_type", result.ContentType),
		slog.Int("response_size", result.ResponseSize),
		slog.String("document_title", result.DocumentTitle),
		slog.String("response_kind", result.ResponseKind),
		slog.String("requested_nm_id", result.RequestedNMID),
		slog.String("parsed_nm_id", result.ParsedNMID),
		slog.Bool("json_decode_success", result.JSONDecodeOK),
		slog.String("resultset", result.Resultset),
		slog.Int("products_count", result.ProductsCount),
	)

	requestedNMID := wbNMIDFromDetailURL(requestURL)
	if requestedNMID != "" {
		var response wbProductsResponse
		if err := json.Unmarshal(result.Body, &response); err != nil {
			return newWBBrowserFallbackError("parser_response_invalid", fmt.Errorf("decode browser upstream WB product JSON: %w", err))
		}
		if _, err := validateWBProductResponse(response, requestedNMID); err != nil {
			return newWBBrowserFallbackError("parser_response_invalid", fmt.Errorf("validate browser upstream WB product: %w", err))
		}
	}
	if err := json.Unmarshal(result.Body, target); err != nil {
		return newWBBrowserFallbackError("parser_response_invalid", fmt.Errorf("decode browser upstream JSON: %w", err))
	}

	return nil
}

func newWBBrowserFallbackError(kind string, err error) error {
	if err == nil {
		return nil
	}
	if strings.TrimSpace(kind) == "" {
		kind = classifyWBBrowserFallbackError(err)
	}
	return &wbBrowserFallbackError{Kind: kind, Err: err}
}

func classifyWBBrowserFallbackError(err error) string {
	if err == nil {
		return "browser_fallback_error"
	}
	errorText := strings.ToLower(err.Error())
	if strings.Contains(errorText, "status 403") || strings.Contains(errorText, "status 498") || strings.Contains(errorText, "antibot") || strings.Contains(errorText, "angie") {
		return "blocked_by_antibot"
	}
	if strings.Contains(errorText, "invalid") || strings.Contains(errorText, "validation") || strings.Contains(errorText, "not wildberries json") || strings.Contains(errorText, "does not contain") || strings.Contains(errorText, "product catalog") {
		return "parser_response_invalid"
	}
	if errors.Is(err, context.DeadlineExceeded) || strings.Contains(errorText, "timeout") || strings.Contains(errorText, "deadline exceeded") {
		return "browser_fallback_timeout"
	}
	return "browser_fallback_error"
}

func wbNMIDFromDetailURL(requestURL string) string {
	parsedURL, err := url.Parse(requestURL)
	if err != nil || (!strings.Contains(parsedURL.Path, "/card/") && !strings.Contains(parsedURL.Path, "/u-card/")) {
		return ""
	}
	return strings.TrimSpace(parsedURL.Query().Get("nm"))
}
