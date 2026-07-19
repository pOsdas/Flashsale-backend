package httpserver

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"go_fetcher/internal/models"
)

type fakeHealthParser struct {
	search func(context.Context, string, int) ([]models.Product, error)
	parse  func(context.Context, string) ([]models.Product, error)
}

func (p fakeHealthParser) SearchProducts(ctx context.Context, query string, limit int) ([]models.Product, error) {
	return p.search(ctx, query, limit)
}

func (p fakeHealthParser) ParseProduct(ctx context.Context, input string) ([]models.Product, error) {
	return p.parse(ctx, input)
}

func healthProduct(sku string) models.Product {
	return models.Product{
		SKU:         sku,
		Title:       "Real product " + sku,
		PriceCents:  10000,
		Available:   1,
		ProductPath: "/product/" + sku,
	}
}

func successfulParser(sku string) fakeHealthParser {
	product := healthProduct(sku)
	return fakeHealthParser{
		search: func(context.Context, string, int) ([]models.Product, error) {
			return []models.Product{product}, nil
		},
		parse: func(context.Context, string) ([]models.Product, error) {
			return []models.Product{product}, nil
		},
	}
}

func newHealthTestServer(wb, ozon ProductSearchParser, marketplaceTimeout, handlerTimeout time.Duration) *Server {
	return NewServer(
		"", "", slog.New(slog.NewTextHandler(io.Discard, nil)), nil, nil, wb, ozon,
		ParserHealthConfig{MarketplaceTimeout: marketplaceTimeout, HandlerTimeout: handlerTimeout},
	)
}

func executeParserHealth(t *testing.T, server *Server, ctx context.Context) ParserHealthResponse {
	t.Helper()
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "/api/v1/parser/health", nil).WithContext(ctx)
	server.handleParserHealth(recorder, request)

	var response ParserHealthResponse
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode health response: %v; body=%s", err, recorder.Body.String())
	}
	return response
}

func TestParserHealthStartsMarketplacesConcurrently(t *testing.T) {
	started := make(chan string, 2)
	release := make(chan struct{})
	parser := func(sku string) fakeHealthParser {
		product := healthProduct(sku)
		return fakeHealthParser{
			search: func(ctx context.Context, _ string, _ int) ([]models.Product, error) {
				started <- sku
				select {
				case <-release:
					return []models.Product{product}, nil
				case <-ctx.Done():
					return nil, ctx.Err()
				}
			},
			parse: func(context.Context, string) ([]models.Product, error) {
				return []models.Product{product}, nil
			},
		}
	}

	server := newHealthTestServer(parser("wb-1"), parser("ozon-1"), time.Second, 2*time.Second)
	type handlerResult struct {
		response ParserHealthResponse
		err      error
	}
	done := make(chan handlerResult, 1)
	startedAt := time.Now()
	go func() {
		recorder := httptest.NewRecorder()
		request := httptest.NewRequest(http.MethodGet, "/api/v1/parser/health", nil)
		server.handleParserHealth(recorder, request)
		var response ParserHealthResponse
		err := json.Unmarshal(recorder.Body.Bytes(), &response)
		done <- handlerResult{response: response, err: err}
	}()

	seen := map[string]bool{}
	deadline := time.NewTimer(300 * time.Millisecond)
	defer deadline.Stop()
	for len(seen) < 2 {
		select {
		case sku := <-started:
			seen[sku] = true
		case <-deadline.C:
			t.Fatal("both marketplace checks did not start concurrently")
		}
	}
	close(release)

	select {
	case result := <-done:
		if result.err != nil {
			t.Fatalf("decode health response: %v", result.err)
		}
		if result.response.Checks["wb"].Status != "ok" || result.response.Checks["ozon"].Status != "ok" {
			t.Fatalf("unexpected checks: %#v", result.response.Checks)
		}
		if elapsed := time.Since(startedAt); elapsed >= 600*time.Millisecond {
			t.Fatalf("parallel health check took %s", elapsed)
		}
	case <-time.After(time.Second):
		t.Fatal("health handler did not finish")
	}
}

func TestParserHealthTimeoutIsIsolatedPerMarketplace(t *testing.T) {
	for _, slowMarketplace := range []string{"wb", "ozon"} {
		t.Run(slowMarketplace, func(t *testing.T) {
			slow := fakeHealthParser{
				search: func(ctx context.Context, _ string, _ int) ([]models.Product, error) {
					<-ctx.Done()
					return nil, ctx.Err()
				},
				parse: func(context.Context, string) ([]models.Product, error) {
					return nil, errors.New("unexpected parse")
				},
			}
			fast := successfulParser("123")
			wb, ozon := ProductSearchParser(slow), ProductSearchParser(fast)
			if slowMarketplace == "ozon" {
				wb, ozon = fast, slow
			}

			response := executeParserHealth(t, newHealthTestServer(wb, ozon, 30*time.Millisecond, 200*time.Millisecond), context.Background())
			if response.Checks[slowMarketplace].Status != "error" {
				t.Fatalf("slow check status = %q", response.Checks[slowMarketplace].Status)
			}
			fastMarketplace := "ozon"
			if slowMarketplace == "ozon" {
				fastMarketplace = "wb"
			}
			if response.Checks[fastMarketplace].Status != "ok" {
				t.Fatalf("fast check status = %q", response.Checks[fastMarketplace].Status)
			}
		})
	}
}

func TestParserHealthRequestCancellationCancelsBothChecks(t *testing.T) {
	var canceled sync.WaitGroup
	canceled.Add(2)
	waitingParser := func() fakeHealthParser {
		return fakeHealthParser{
			search: func(ctx context.Context, _ string, _ int) ([]models.Product, error) {
				<-ctx.Done()
				canceled.Done()
				return nil, ctx.Err()
			},
			parse: func(context.Context, string) ([]models.Product, error) { return nil, nil },
		}
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	executeParserHealth(t, newHealthTestServer(waitingParser(), waitingParser(), time.Second, 2*time.Second), ctx)

	done := make(chan struct{})
	go func() { canceled.Wait(); close(done) }()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("request cancellation did not cancel both checks")
	}
}
