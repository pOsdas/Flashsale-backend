package config

import (
	"fmt"
	"os"
	"time"
)

type Config struct {
	DjangoURL     string
	FetcherAPIKey string
	WBCookie      string
	Timeout       time.Duration
}

func Load() (*Config, error) {
	cfg := &Config{
		DjangoURL:     os.Getenv("DJANGO_URL"),
		FetcherAPIKey: os.Getenv("FETCHER_API_KEY"),
		WBCookie:      os.Getenv("WB_COOKIE"),
		Timeout:       30 * time.Second,
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

	return cfg, nil
}
