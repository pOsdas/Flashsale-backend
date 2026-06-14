package ozon

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"
)

func setOzonHeaders(req *http.Request, cookie string) {
	req.Header.Set("Accept", "application/json, text/plain, */*")
	req.Header.Set("Accept-Language", "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7")
	req.Header.Set("Connection", "keep-alive")
	req.Header.Set("Referer", "https://www.ozon.ru/")
	req.Header.Set("Sec-Fetch-Dest", "empty")
	req.Header.Set("Sec-Fetch-Mode", "cors")
	req.Header.Set("Sec-Fetch-Site", "same-origin")
	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")
	req.Header.Set("sec-ch-ua", `"Chromium";v="148", "Google Chrome";v="148", "Not-A.Brand";v="99"`)
	req.Header.Set("sec-ch-ua-mobile", "?0")
	req.Header.Set("sec-ch-ua-platform", `"Windows"`)

	if strings.TrimSpace(cookie) != "" {
		req.Header.Set("Cookie", cookie)
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

	setOzonHeaders(req, p.currentCookie())

	resp, err := p.client.Do(req)
	if err != nil {
		return fmt.Errorf("execute request: %w", err)
	}
	defer resp.Body.Close()

	responseBody, err := io.ReadAll(resp.Body)
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
