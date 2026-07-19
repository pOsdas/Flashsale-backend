package wildberries

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestDoJSONRequestUsesBrowserFallbackOnForbidden(t *testing.T) {
	requestTimeoutMS := make(chan int64, 1)
	browserServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != wbBrowserFetchPath {
			http.NotFound(w, r)
			return
		}

		var requestBody struct {
			RequestTimeoutMS int64 `json:"request_timeout_ms"`
		}
		if err := json.NewDecoder(r.Body).Decode(&requestBody); err != nil {
			t.Errorf("decode browser request: %v", err)
		}
		requestTimeoutMS <- requestBody.RequestTimeoutMS
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"status_code": http.StatusOK,
			"body":        map[string]any{"value": "from-browser"},
		})
	}))
	defer browserServer.Close()

	httpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
		_, _ = w.Write([]byte("<html><center>Angie</center></html>"))
	}))
	defer httpServer.Close()

	parser := NewParser(ParserConfig{
		BrowserFetcherEnabled: true,
		BrowserFetcherURL:     browserServer.URL,
		BrowserFetcherTimeout: time.Second,
	}, nil)
	parser.client = httpServer.Client()

	var target struct {
		Value string `json:"value"`
	}
	if err := parser.doJSONRequest(context.Background(), httpServer.URL, &target); err != nil {
		t.Fatalf("doJSONRequest returned error: %v", err)
	}
	if target.Value != "from-browser" {
		t.Fatalf("Value = %q, want from-browser", target.Value)
	}
	if got := <-requestTimeoutMS; got <= 0 || got > 1000 {
		t.Fatalf("request_timeout_ms = %d, want 1..1000", got)
	}
}

func TestDoJSONRequestPreservesBrowserFallbackAsFinalErrorSource(t *testing.T) {
	browserServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusInternalServerError)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"error":      "captured HTTP 200 JSON failed product catalog validation",
			"error_type": "parser_response_invalid",
		})
	}))
	defer browserServer.Close()

	httpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
		_, _ = w.Write([]byte("<html><center>Angie</center></html>"))
	}))
	defer httpServer.Close()

	parser := NewParser(ParserConfig{
		BrowserFetcherEnabled: true,
		BrowserFetcherURL:     browserServer.URL,
		BrowserFetcherTimeout: time.Second,
	}, nil)
	parser.client = httpServer.Client()

	err := parser.doJSONRequest(context.Background(), httpServer.URL, &struct{}{})
	var combined *wbHTTPAndBrowserFallbackError
	if !errors.As(err, &combined) {
		t.Fatalf("expected combined fallback error, got %T: %v", err, err)
	}
	if combined.BrowserFallbackKind != "parser_response_invalid" {
		t.Fatalf("fallback kind = %q", combined.BrowserFallbackKind)
	}
	if blocked, _, _ := parser.isTemporarilyBlocked(); blocked {
		t.Fatal("parser must not be marked antibot-blocked after HTTP 200 validation failure")
	}
	details := combined.ParserDetails()
	if details["final_error_source"] != "browser_fallback" {
		t.Fatalf("unexpected details: %#v", details)
	}
	if details["http_parser_error"] == "" || details["browser_fallback_error"] == "" {
		t.Fatalf("both causes must be preserved: %#v", details)
	}
	wrappedDetails := parser.withRequestDetails(err, httpServer.URL).(*parserRequestError).ParserDetails()
	if wrappedDetails["final_error_source"] != "browser_fallback" || wrappedDetails["browser_fallback_error_type"] != "parser_response_invalid" {
		t.Fatalf("request wrapper lost fallback details: %#v", wrappedDetails)
	}
}

func TestSetWBHeadersUsesConsistentEdgeProfile(t *testing.T) {
	req, err := http.NewRequest(http.MethodGet, buildDetailURL("302421341"), nil)
	if err != nil {
		t.Fatal(err)
	}

	setWBHeaders(req, "session=value")

	if !strings.Contains(req.Header.Get("User-Agent"), "Edg/148.") {
		t.Fatalf("User-Agent does not identify Edge: %q", req.Header.Get("User-Agent"))
	}

	clientHints := req.Header.Get("sec-ch-ua")
	if !strings.Contains(clientHints, `"Microsoft Edge";v="148"`) {
		t.Fatalf("Client Hints do not identify the same Edge version: %q", clientHints)
	}

	if got := req.Header.Get("Cookie"); got != "session=value" {
		t.Fatalf("Cookie = %q, want %q", got, "session=value")
	}
}

func TestSetWBHeadersUsesProductReferer(t *testing.T) {
	req, err := http.NewRequest(http.MethodGet, buildDetailURL("302421341"), nil)
	if err != nil {
		t.Fatal(err)
	}

	setWBHeaders(req, "")

	want := "https://www.wildberries.ru/catalog/302421341/detail.aspx"
	if got := req.Header.Get("Referer"); got != want {
		t.Fatalf("Referer = %q, want %q", got, want)
	}
}

func TestSetWBHeadersPreservesActualSearchQueryInReferer(t *testing.T) {
	req, err := http.NewRequest(http.MethodGet, buildSearchURL("iphone", 1), nil)
	if err != nil {
		t.Fatal(err)
	}

	setWBHeaders(req, "")

	want := "https://www.wildberries.ru/catalog/0/search.aspx?search=iphone"
	if got := req.Header.Get("Referer"); got != want {
		t.Fatalf("Referer = %q, want %q", got, want)
	}
}

func TestSetWBHeadersUsesNeutralRefererForCategory(t *testing.T) {
	req, err := http.NewRequest(http.MethodGet, buildCategoryURL("кошельки", 1), nil)
	if err != nil {
		t.Fatal(err)
	}

	setWBHeaders(req, "")

	want := "https://www.wildberries.ru/"
	if got := req.Header.Get("Referer"); got != want {
		t.Fatalf("Referer = %q, want %q", got, want)
	}
}
