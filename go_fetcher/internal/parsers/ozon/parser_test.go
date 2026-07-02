package ozon

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return f(req)
}

func TestParseProductHTTPParserSuccessSkipsFallback(t *testing.T) {
	var browserCalls int32
	browserServer := newBrowserProductServer(t, &browserCalls, 0, http.StatusOK)
	defer browserServer.Close()

	parser, _ := newTestParser(browserServer.URL)
	parser.client.Transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		return jsonResponse(http.StatusOK, validOzonProductPageResponse("1665454433")), nil
	})

	products, err := parser.ParseProduct(context.Background(), "/product/test-product-1665454433/")
	if err != nil {
		t.Fatalf("ParseProduct returned error: %v", err)
	}

	if len(products) != 1 || products[0].SKU != "1665454433" {
		t.Fatalf("expected parsed HTTP product, got %#v", products)
	}

	if got := atomic.LoadInt32(&browserCalls); got != 0 {
		t.Fatalf("expected fallback not to be called, got %d calls", got)
	}
}

func TestParseProductHTTPParserErrorFallbackSuccess(t *testing.T) {
	var browserCalls int32
	browserServer := newBrowserProductServer(t, &browserCalls, 0, http.StatusOK)
	defer browserServer.Close()

	parser, _ := newTestParser(browserServer.URL)
	parser.client.Transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		return jsonResponse(http.StatusInternalServerError, `{"error":"temporary ozon error"}`), nil
	})

	products, err := parser.ParseProduct(context.Background(), "/product/test-product-1665454433/")
	if err != nil {
		t.Fatalf("ParseProduct returned error: %v", err)
	}

	if len(products) != 1 || products[0].SKU != "1665454433" {
		t.Fatalf("expected browser fallback product, got %#v", products)
	}

	if got := atomic.LoadInt32(&browserCalls); got != 1 {
		t.Fatalf("expected fallback to be called once, got %d calls", got)
	}
}

func TestParseProductHTTPParserLocalDeadlineAllowsFallback(t *testing.T) {
	var browserCalls int32
	browserServer := newBrowserProductServer(t, &browserCalls, 0, http.StatusOK)
	defer browserServer.Close()

	parser, _ := newTestParser(browserServer.URL)
	parser.httpParserTimeout = 10 * time.Millisecond
	parser.client.Timeout = parser.httpParserTimeout
	parser.client.Transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		<-req.Context().Done()
		return nil, req.Context().Err()
	})

	products, err := parser.ParseProduct(context.Background(), "/product/test-product-1665454433/")
	if err != nil {
		t.Fatalf("ParseProduct returned error: %v", err)
	}

	if len(products) != 1 || products[0].SKU != "1665454433" {
		t.Fatalf("expected browser fallback product, got %#v", products)
	}

	if got := atomic.LoadInt32(&browserCalls); got != 1 {
		t.Fatalf("expected fallback to run after local HTTP timeout, got %d calls", got)
	}
}

func TestParseProductParentCanceledDuringHTTPParserSkipsFallback(t *testing.T) {
	var browserCalls int32
	browserServer := newBrowserProductServer(t, &browserCalls, 0, http.StatusOK)
	defer browserServer.Close()

	parser, logs := newTestParser(browserServer.URL)
	parser.httpParserTimeout = time.Second
	parser.client.Timeout = parser.httpParserTimeout

	parentCtx, cancelParent := context.WithCancel(context.Background())
	parser.client.Transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		cancelParent()
		<-req.Context().Done()
		return nil, req.Context().Err()
	})

	_, err := parser.ParseProduct(parentCtx, "/product/test-product-1665454433/")
	if err == nil {
		t.Fatal("expected ParseProduct error")
	}

	if !errors.Is(err, context.Canceled) {
		t.Fatalf("expected context.Canceled in error chain, got %v", err)
	}

	if got := atomic.LoadInt32(&browserCalls); got != 0 {
		t.Fatalf("expected fallback to be skipped, got %d calls", got)
	}

	logText := logs.String()
	if !strings.Contains(logText, "ozon browser fallback skipped") ||
		!strings.Contains(logText, "fallback_reason=parent_context_canceled") {
		t.Fatalf("expected skipped fallback log, got %s", logText)
	}

	if strings.Contains(logText, "ozon browser fallback failed") {
		t.Fatalf("did not expect false fallback failure log, got %s", logText)
	}
}

func TestParseProductParentDeadlineExceededSkipsFallback(t *testing.T) {
	var browserCalls int32
	browserServer := newBrowserProductServer(t, &browserCalls, 0, http.StatusOK)
	defer browserServer.Close()

	parser, logs := newTestParser(browserServer.URL)
	parser.httpParserTimeout = time.Second
	parser.client.Timeout = parser.httpParserTimeout
	parser.client.Transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		<-req.Context().Done()
		return nil, req.Context().Err()
	})

	parentCtx, cancelParent := context.WithTimeout(context.Background(), 10*time.Millisecond)
	defer cancelParent()

	_, err := parser.ParseProduct(parentCtx, "/product/test-product-1665454433/")
	if err == nil {
		t.Fatal("expected ParseProduct error")
	}

	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("expected context.DeadlineExceeded in error chain, got %v", err)
	}

	if got := atomic.LoadInt32(&browserCalls); got != 0 {
		t.Fatalf("expected fallback to be skipped, got %d calls", got)
	}

	if logText := logs.String(); !strings.Contains(logText, "fallback_reason=parent_deadline_exceeded") {
		t.Fatalf("expected parent deadline skipped log, got %s", logText)
	}
}

func TestParseProductBrowserFallbackGetsOwnTimeout(t *testing.T) {
	var browserCalls int32
	browserServer := newBrowserProductServer(t, &browserCalls, 200*time.Millisecond, http.StatusOK)
	defer browserServer.Close()

	parser, logs := newTestParser(browserServer.URL)
	parser.browserFetcherTimeout = 10 * time.Millisecond
	parser.browserClient.timeout = parser.browserFetcherTimeout
	parser.browserClient.client.Timeout = parser.browserFetcherTimeout
	parser.client.Transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		return jsonResponse(http.StatusInternalServerError, `{"error":"temporary ozon error"}`), nil
	})

	_, err := parser.ParseProduct(context.Background(), "/product/test-product-1665454433/")
	if err == nil {
		t.Fatal("expected ParseProduct error")
	}

	if got := atomic.LoadInt32(&browserCalls); got != 1 {
		t.Fatalf("expected fallback to be called once, got %d calls", got)
	}

	if logText := logs.String(); !strings.Contains(logText, "fallback_reason=browser_fallback_local_timeout") {
		t.Fatalf("expected browser fallback timeout log, got %s", logText)
	}
}

func TestParseProductBothStagesFailReportsBothReasons(t *testing.T) {
	var browserCalls int32
	browserServer := newBrowserProductServer(t, &browserCalls, 0, http.StatusInternalServerError)
	defer browserServer.Close()

	parser, _ := newTestParser(browserServer.URL)
	parser.client.Transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
		return jsonResponse(http.StatusInternalServerError, `{"error":"temporary ozon error"}`), nil
	})

	_, err := parser.ParseProduct(context.Background(), "/product/test-product-1665454433/")
	if err == nil {
		t.Fatal("expected ParseProduct error")
	}

	errorText := err.Error()
	if !strings.Contains(errorText, "parse Ozon product with HTTP failed") ||
		!strings.Contains(errorText, "browser fallback failed") {
		t.Fatalf("expected both failure reasons, got %v", err)
	}

	if got := atomic.LoadInt32(&browserCalls); got != 1 {
		t.Fatalf("expected fallback to be called once, got %d calls", got)
	}
}

func TestParentContextDoneSkipsFallbackForProductSearchAndCategory(t *testing.T) {
	testCases := []struct {
		name string
		run  func(context.Context, *Parser) error
	}{
		{
			name: "product",
			run: func(ctx context.Context, parser *Parser) error {
				_, err := parser.ParseProduct(ctx, "/product/test-product-1665454433/")
				return err
			},
		},
		{
			name: "search",
			run: func(ctx context.Context, parser *Parser) error {
				_, err := parser.SearchProducts(ctx, "iphone", 1)
				return err
			},
		},
		{
			name: "category",
			run: func(ctx context.Context, parser *Parser) error {
				_, err := parser.CategoryProducts(ctx, "/category/smartfony-15502/", 1)
				return err
			},
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			var browserCalls int32
			browserServer := newBrowserListServer(t, &browserCalls)
			defer browserServer.Close()

			parser, logs := newTestParser(browserServer.URL)
			parser.client.Transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
				if err := req.Context().Err(); err != nil {
					return nil, err
				}

				return nil, context.Canceled
			})

			ctx, cancel := context.WithCancel(context.Background())
			cancel()

			err := tc.run(ctx, parser)
			if err == nil {
				t.Fatal("expected parser error")
			}

			if got := atomic.LoadInt32(&browserCalls); got != 0 {
				t.Fatalf("expected fallback to be skipped, got %d calls", got)
			}

			logText := logs.String()
			if !strings.Contains(logText, "ozon browser fallback skipped") {
				t.Fatalf("expected skipped fallback log, got %s", logText)
			}

			if strings.Contains(logText, "ozon browser fallback failed") {
				t.Fatalf("did not expect false fallback failure log, got %s", logText)
			}
		})
	}
}

func newTestParser(browserURL string) (*Parser, *bytes.Buffer) {
	var logs bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&logs, &slog.HandlerOptions{
		Level: slog.LevelDebug,
	}))

	parser := NewParser(ParserConfig{
		HTTPParserTimeout:     100 * time.Millisecond,
		BrowserFetcherURL:     browserURL,
		BrowserFetcherEnabled: true,
		BrowserFetcherTimeout: 100 * time.Millisecond,
	}, logger)
	parser.requestDelay = 0
	parser.maxRetries = 0

	return parser, &logs
}

func newBrowserProductServer(t *testing.T, calls *int32, wait time.Duration, statusCode int) *httptest.Server {
	t.Helper()

	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(calls, 1)

		if wait > 0 {
			timer := time.NewTimer(wait)
			defer timer.Stop()

			select {
			case <-r.Context().Done():
				return
			case <-timer.C:
			}
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(statusCode)

		if statusCode >= 200 && statusCode < 300 {
			_, _ = io.WriteString(w, `{"status":"ok","product":{"external_id":"1665454433","sku":"1665454433","title":"Browser Product","price_cents":12300,"currency":"RUB","available":1,"is_active":true,"url":"https://www.ozon.ru/product/test-product-1665454433/","product_path":"/product/test-product-1665454433/"}}`)
			return
		}

		_, _ = io.WriteString(w, `{"error":"browser fetcher failed"}`)
	}))
}

func newBrowserListServer(t *testing.T, calls *int32) *httptest.Server {
	t.Helper()

	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(calls, 1)
		w.Header().Set("Content-Type", "application/json")

		if strings.HasSuffix(r.URL.Path, ozonBrowserProductPath) {
			_, _ = io.WriteString(w, `{"status":"ok","product":{"external_id":"1665454433","sku":"1665454433","title":"Browser Product","price_cents":12300,"currency":"RUB","available":1,"is_active":true}}`)
			return
		}

		_, _ = io.WriteString(w, `[{"external_id":"1665454433","sku":"1665454433","title":"Browser Product","price_cents":12300,"currency":"RUB","available":1,"is_active":true}]`)
	}))
}

func jsonResponse(statusCode int, body string) *http.Response {
	return &http.Response{
		StatusCode: statusCode,
		Header:     make(http.Header),
		Body:       io.NopCloser(strings.NewReader(body)),
	}
}

func validOzonProductPageResponse(sku string) string {
	return fmt.Sprintf(
		`{"widgetStates":{"webProductMainWidget-1":"{\"sku\":\"%s\",\"url\":\"/product/test-product-%s/\"}","webAspects-1":"{\"aspects\":[{\"variants\":[{\"sku\":\"%s\",\"availability\":\"inStock\",\"price\":123,\"data\":{\"title\":\"HTTP Product\"}}]}]}"}}`,
		sku,
		sku,
		sku,
	)
}
