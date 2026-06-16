package ozon

import (
	"compress/gzip"
	"compress/zlib"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"
)

func applyOzonPageAPIHeaders(req *http.Request, cookieHeader string, referer string) {
	req.Header.Set("User-Agent", ozonUserAgent)
	req.Header.Set("Accept", "application/json, text/plain, */*")
	req.Header.Set("Accept-Language", "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7")
	req.Header.Set("Accept-Encoding", "gzip, deflate")
	req.Header.Set("Cache-Control", "no-cache")
	req.Header.Set("Pragma", "no-cache")

	req.Header.Set("Origin", "https://www.ozon.ru")

	if strings.TrimSpace(referer) != "" {
		req.Header.Set("Referer", referer)
	} else {
		req.Header.Set("Referer", "https://www.ozon.ru/")
	}

	req.Header.Set("Sec-Ch-Ua", `"Microsoft Edge";v="125", "Chromium";v="125", "Not.A/Brand";v="24"`)
	req.Header.Set("Sec-Ch-Ua-Mobile", "?0")
	req.Header.Set("Sec-Ch-Ua-Platform", `"Windows"`)

	req.Header.Set("Sec-Fetch-Dest", "empty")
	req.Header.Set("Sec-Fetch-Mode", "cors")
	req.Header.Set("Sec-Fetch-Site", "same-origin")

	if strings.TrimSpace(cookieHeader) != "" {
		req.Header.Set("Cookie", strings.TrimSpace(cookieHeader))
	}
}

func isRetryableOzonError(err error) bool {
	httpErr, ok := err.(*ozonHTTPError)
	if !ok {
		return false
	}

	return httpErr.StatusCode == http.StatusTooManyRequests ||
		httpErr.StatusCode >= 503
}

func readOzonResponseBody(resp *http.Response) ([]byte, error) {
	switch strings.ToLower(strings.TrimSpace(resp.Header.Get("Content-Encoding"))) {
	case "", "identity":
		return io.ReadAll(resp.Body)
	case "gzip":
		reader, err := gzip.NewReader(resp.Body)
		if err != nil {
			return nil, fmt.Errorf("create gzip reader: %w", err)
		}
		defer reader.Close()

		return io.ReadAll(reader)
	case "deflate":
		reader, err := zlib.NewReader(resp.Body)
		if err != nil {
			return nil, fmt.Errorf("create deflate reader: %w", err)
		}
		defer reader.Close()

		return io.ReadAll(reader)
	default:
		return nil, fmt.Errorf("unsupported response content encoding: %s", resp.Header.Get("Content-Encoding"))
	}
}

func (p *Parser) doJSONRequest(ctx context.Context, requestURL string, target any) error {
	var lastErr error

	for attempt := 0; attempt <= p.maxRetries; attempt++ {
		if attempt > 0 {
			delay := p.retryDelay(attempt)

			p.logger.Warn(
				"ozon request retry",
				slog.Int("attempt", attempt),
				slog.Duration("delay", delay),
				slog.String("url", requestURL),
				slog.String("error", lastErr.Error()),
			)

			if err := sleepWithContext(ctx, delay); err != nil {
				return err
			}
		} else if p.requestDelay > 0 {
			if err := sleepWithContext(ctx, p.requestDelay); err != nil {
				return err
			}
		}

		err := p.doJSONRequestOnce(ctx, requestURL, target)
		if err == nil {
			return nil
		}

		lastErr = err

		if !isRetryableOzonError(err) {
			return err
		}
	}

	return fmt.Errorf("request failed after %d retries: %w", p.maxRetries, lastErr)
}

func (p *Parser) doJSONRequestOnce(ctx context.Context, requestURL string, target any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, requestURL, nil)
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}

	applyOzonPageAPIHeaders(req, p.currentCookie(), "")

	resp, err := p.client.Do(req)
	if err != nil {
		return fmt.Errorf("execute request: %w", err)
	}
	defer resp.Body.Close()

	responseBody, err := readOzonResponseBody(resp)
	if err != nil {
		return fmt.Errorf("read Ozon response body: %w", err)
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return &ozonHTTPError{
			StatusCode: resp.StatusCode,
			Body:       limitString(string(responseBody), 1000),
		}
	}

	if err := json.Unmarshal(responseBody, target); err != nil {
		return fmt.Errorf("decode response: %w, body: %s", err, string(responseBody))
	}

	return nil
}

func (p *Parser) retryDelay(attempt int) time.Duration {
	multiplier := 1 << (attempt - 1)
	return time.Duration(multiplier) * p.retryBaseDelay
}

func sleepWithContext(ctx context.Context, delay time.Duration) error {
	timer := time.NewTimer(delay)
	defer timer.Stop()

	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

func (e *ozonHTTPError) Error() string {
	return fmt.Sprintf("unexpected Ozon status code: %d, body: %s", e.StatusCode, e.Body)
}
