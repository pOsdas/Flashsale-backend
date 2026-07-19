package config

import "testing"

func prepareRequiredConfig(t *testing.T) {
	t.Helper()
	t.Setenv("DJANGO_URL", "http://backend:8000")
	t.Setenv("FETCHER_API_KEY", "test-key")
	t.Setenv("PARSER_HEALTH_MARKETPLACE_TIMEOUT_SECONDS", "")
	t.Setenv("PARSER_HEALTH_HANDLER_TIMEOUT_SECONDS", "")
}

func TestLoadParserHealthTimeoutDefaults(t *testing.T) {
	prepareRequiredConfig(t)

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load returned error: %v", err)
	}
	if cfg.ParserHealthMarketplaceTimeoutSeconds != 90 {
		t.Fatalf("marketplace timeout = %d, want 90", cfg.ParserHealthMarketplaceTimeoutSeconds)
	}
	if cfg.ParserHealthHandlerTimeoutSeconds != 100 {
		t.Fatalf("handler timeout = %d, want 100", cfg.ParserHealthHandlerTimeoutSeconds)
	}
}

func TestLoadRejectsParserHealthHandlerTimeoutNotGreaterThanMarketplaceTimeout(t *testing.T) {
	prepareRequiredConfig(t)
	t.Setenv("PARSER_HEALTH_MARKETPLACE_TIMEOUT_SECONDS", "90")
	t.Setenv("PARSER_HEALTH_HANDLER_TIMEOUT_SECONDS", "90")

	if _, err := Load(); err == nil {
		t.Fatal("Load returned nil error")
	}
}

func TestLoadRejectsNonPositiveParserHealthMarketplaceTimeout(t *testing.T) {
	prepareRequiredConfig(t)
	t.Setenv("PARSER_HEALTH_MARKETPLACE_TIMEOUT_SECONDS", "0")

	if _, err := Load(); err == nil {
		t.Fatal("Load returned nil error")
	}
}
