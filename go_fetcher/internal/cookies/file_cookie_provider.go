package cookies

import (
	"os"
	"strings"
	"sync"
	"time"
)

type Provider interface {
	GetCookie() string
	ForceReload()
	Source() string
	IsPresent() bool
}

type FileCookieProvider struct {
	path       string
	ttl        time.Duration
	mu         sync.RWMutex
	value      string
	lastLoaded time.Time
}

func NewFileCookieProvider(path string, ttl time.Duration) *FileCookieProvider {
	if ttl <= 0 {
		ttl = 30 * time.Second
	}

	return &FileCookieProvider{
		path: path,
		ttl:  ttl,
	}
}

func (p *FileCookieProvider) GetCookie() string {
	if p == nil {
		return ""
	}

	p.mu.RLock()

	if p.value != "" && time.Since(p.lastLoaded) < p.ttl {
		value := p.value
		p.mu.RUnlock()
		return value
	}

	p.mu.RUnlock()

	p.mu.Lock()
	defer p.mu.Unlock()

	if p.value != "" && time.Since(p.lastLoaded) < p.ttl {
		return p.value
	}

	p.loadLocked()

	return p.value
}

func (p *FileCookieProvider) ForceReload() {
	if p == nil {
		return
	}

	p.mu.Lock()
	defer p.mu.Unlock()

	p.loadLocked()
}

func (p *FileCookieProvider) Source() string {
	if p == nil {
		return ""
	}

	return p.path
}

func (p *FileCookieProvider) IsPresent() bool {
	return strings.TrimSpace(p.GetCookie()) != ""
}

func (p *FileCookieProvider) loadLocked() {
	raw, err := os.ReadFile(p.path)
	if err != nil {
		p.value = ""
		p.lastLoaded = time.Now()
		return
	}

	p.value = strings.TrimSpace(string(raw))
	p.lastLoaded = time.Now()
}
