package config

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

type Config struct {
	DjangoURL     string
	FetcherAPIKey string
	WBCookie      string
	OzonCookie    string

	Timeout time.Duration

	WBRequestDelay   time.Duration
	WBMaxRetries     int
	WBRetryBaseDelay time.Duration

	OzonRequestDelay   time.Duration
	OzonMaxRetries     int
	OzonRetryBaseDelay time.Duration
}

func Load() (*Config, error) {
	cfg := &Config{
		DjangoURL:     os.Getenv("DJANGO_URL"),
		FetcherAPIKey: os.Getenv("FETCHER_API_KEY"),
		WBCookie:      os.Getenv("WB_COOKIE"),
		OzonCookie:    os.Getenv("OZON_COOKIE"),

		Timeout: 30 * time.Second,

		WBRequestDelay:   getEnvDurationMS("WB_REQUEST_DELAY_MS", 700*time.Millisecond),
		WBMaxRetries:     getEnvInt("WB_MAX_RETRIES", 3),
		WBRetryBaseDelay: getEnvDurationMS("WB_RETRY_BASE_DELAY_MS", 1*time.Second),

		OzonRequestDelay:   getEnvDurationMS("OZON_REQUEST_DELAY_MS", 700*time.Millisecond),
		OzonMaxRetries:     getEnvInt("OZON_MAX_RETRIES", 3),
		OzonRetryBaseDelay: getEnvDurationMS("OZON_RETRY_BASE_DELAY_MS", 1*time.Second),
	}

	if cfg.DjangoURL == "" {
		return nil, fmt.Errorf("DJANGO_URL is required")
	}

	if cfg.FetcherAPIKey == "" {
		return nil, fmt.Errorf("FETCHER_API_KEY is required")
	}

	if cfg.WBCookie == "" {
		return nil, fmt.Errorf("WB_COOKIE is required")
	}

	if cfg.WBMaxRetries < 0 {
		return nil, fmt.Errorf("WB_MAX_RETRIES must be greater than or equal to zero")
	}

	return cfg, nil
}

func getEnvInt(key string, defaultValue int) int {
	rawValue := os.Getenv(key)
	if rawValue == "" {
		return defaultValue
	}

	value, err := strconv.Atoi(rawValue)
	if err != nil {
		return defaultValue
	}

	return value
}

func getEnvDurationMS(key string, defaultValue time.Duration) time.Duration {
	rawValue := os.Getenv(key)
	if rawValue == "" {
		return defaultValue
	}

	value, err := strconv.Atoi(rawValue)
	if err != nil {
		return defaultValue
	}

	return time.Duration(value) * time.Millisecond
}
