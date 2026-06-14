package wildberries

import "testing"

type stubCookieProvider struct {
	cookie string
	source string
}

func (p stubCookieProvider) GetCookie() string {
	return p.cookie
}

func (p stubCookieProvider) ForceReload() {}

func (p stubCookieProvider) Source() string {
	return p.source
}

func (p stubCookieProvider) IsPresent() bool {
	return p.cookie != ""
}

func TestCurrentCookieUsesProviderEvenWhenConfiguredCookieExists(t *testing.T) {
	parser := NewParser(ParserConfig{
		Cookie: " env-cookie ",
		CookieProvider: stubCookieProvider{
			cookie: " file-cookie ",
			source: "empty-file",
		},
	}, nil)

	if got := parser.currentCookie(); got != "file-cookie" {
		t.Fatalf("expected file cookie, got %q", got)
	}

	if got := parser.cookieSource(); got != "empty-file" {
		t.Fatalf("expected file cookie source, got %q", got)
	}
}
