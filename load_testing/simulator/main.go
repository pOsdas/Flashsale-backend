package main

import (
	"context"
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"math"
	"math/rand"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

type profile struct {
	Name              string  `json:"name"`
	MinLatencyMS      int     `json:"min_latency_ms"`
	MaxLatencyMS      int     `json:"max_latency_ms"`
	FetchError        float64 `json:"fetch_error_rate"`
	FetchTimeout      float64 `json:"fetch_timeout_rate"`
	FetchRateLimit    float64 `json:"fetch_rate_limit_rate"`
	TelegramError     float64 `json:"telegram_error_rate"`
	TelegramRateLimit float64 `json:"telegram_rate_limit_rate"`
}

var profiles = map[string]profile{
	"fast": {
		Name: "fast", MinLatencyMS: 5, MaxLatencyMS: 20,
	},
	"normal": {
		Name: "normal", MinLatencyMS: 80, MaxLatencyMS: 250,
		FetchError: 0.002, TelegramError: 0.002,
	},
	"realistic": {
		Name: "realistic", MinLatencyMS: 100, MaxLatencyMS: 900,
		FetchError: 0.01, FetchTimeout: 0.005, FetchRateLimit: 0.005,
		TelegramError: 0.005, TelegramRateLimit: 0.005,
	},
	"slow": {
		Name: "slow", MinLatencyMS: 1000, MaxLatencyMS: 3000,
		FetchError: 0.01, TelegramError: 0.01,
	},
	"degraded": {
		Name: "degraded", MinLatencyMS: 300, MaxLatencyMS: 1800,
		FetchError: 0.10, FetchTimeout: 0.05, FetchRateLimit: 0.05,
		TelegramError: 0.08, TelegramRateLimit: 0.07,
	},
	"outage": {
		Name: "outage", MinLatencyMS: 100, MaxLatencyMS: 300,
		FetchError: 1.0, TelegramError: 1.0,
	},
	"antibot": {
		Name: "antibot", MinLatencyMS: 100, MaxLatencyMS: 400,
		FetchRateLimit: 0.80, FetchError: 0.20,
	},
	"telegram_429": {
		Name: "telegram_429", MinLatencyMS: 50, MaxLatencyMS: 200,
		TelegramRateLimit: 1.0,
	},
}

type simulatorState struct {
	mu               sync.RWMutex
	Profile          profile    `json:"profile"`
	PriceMultiplier  float64    `json:"price_multiplier"`
	PriceVersion     int64      `json:"price_version"`
	StartedAt        time.Time  `json:"started_at"`
	LastPriceShockAt *time.Time `json:"last_price_shock_at,omitempty"`
}

var state = simulatorState{
	Profile: profiles["normal"], PriceMultiplier: 1.0,
	StartedAt: time.Now().UTC(),
}

var requestSequence atomic.Uint64
var fetchSuccess atomic.Uint64
var fetchErrors atomic.Uint64
var fetchRateLimited atomic.Uint64
var fetchTimeouts atomic.Uint64
var telegramSuccess atomic.Uint64
var telegramErrors atomic.Uint64
var telegramRateLimited atomic.Uint64
var grafanaAlerts atomic.Uint64
var activeRequests atomic.Int64
var totalLatencyMicros atomic.Uint64
var totalRequests atomic.Uint64
var telegramUpdatesQueued atomic.Uint64
var telegramUpdatesDelivered atomic.Uint64
var telegramDuplicateMessages atomic.Uint64

var telegramReplies = struct {
	mu   sync.Mutex
	seen map[string]time.Time
}{seen: make(map[string]time.Time)}

type telegramUpdateInput struct {
	ChatID any    `json:"chat_id"`
	Text   string `json:"text"`
}

type telegramUpdateQueue struct {
	mu      sync.Mutex
	updates []map[string]any
	nextID  int64
	notify  chan struct{}
}

func newTelegramUpdateQueue() *telegramUpdateQueue {
	return &telegramUpdateQueue{nextID: 1, notify: make(chan struct{})}
}

var telegramUpdates = newTelegramUpdateQueue()

type fetchRequest struct {
	Marketplace string `json:"marketplace"`
	URL         string `json:"url"`
	ExternalID  string `json:"external_id"`
}

type telegramRequest struct {
	ChatID any    `json:"chat_id"`
	Text   string `json:"text"`
}

func main() {
	handler := newHandler()
	address := envOr("LOAD_SIMULATOR_ADDRESS", ":8099")
	server := &http.Server{
		Addr:              address,
		Handler:           handler,
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       75 * time.Second,
		WriteTimeout:      75 * time.Second,
		IdleTimeout:       120 * time.Second,
	}

	log.Printf("load simulator listening on %s", address)
	if err := server.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
}

func newHandler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthHandler)
	mux.HandleFunc("/metrics", metricsHandler)
	mux.HandleFunc("/api/v1/fetch/product/", fetchHandler)
	mux.HandleFunc("/api/v1/fetch/product", fetchHandler)
	mux.HandleFunc("/__control/state", stateHandler)
	mux.HandleFunc("/__control/reset", resetHandler)
	mux.HandleFunc("/__control/profile", profileHandler)
	mux.HandleFunc("/__control/price-shock", priceShockHandler)
	mux.HandleFunc("/__control/grafana-alerts", grafanaAlertHandler)
	mux.HandleFunc("/__control/telegram-updates", telegramUpdatesHandler)
	mux.HandleFunc("/", rootHandler)
	return requestMetricsMiddleware(mux)
}

func requestMetricsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		started := time.Now()
		totalRequests.Add(1)
		activeRequests.Add(1)
		defer func() {
			activeRequests.Add(-1)
			totalLatencyMicros.Add(uint64(time.Since(started).Microseconds()))
		}()
		next.ServeHTTP(w, r)
	})
}

func healthHandler(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"status":  "ok",
		"profile": currentProfile().Name,
	})
}

func fetchHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"status": "error", "error": "method not allowed"})
		return
	}

	var req fetchRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"status": "error", "error": "invalid JSON"})
		return
	}
	if req.Marketplace != "wb" && req.Marketplace != "ozon" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"status": "error", "error": "unsupported marketplace"})
		return
	}

	p := currentProfile()
	sleepProfileLatency(p)
	roll := deterministicRoll(req.Marketplace + req.URL + strconv.FormatUint(requestSequence.Add(1), 10))

	switch {
	case roll < p.FetchTimeout:
		fetchTimeouts.Add(1)
		timeout := envDuration("LOAD_SIMULATOR_TIMEOUT_DURATION", 65*time.Second)
		time.Sleep(timeout)
		writeJSON(w, http.StatusGatewayTimeout, map[string]any{"status": "error", "error": "simulated timeout"})
		return
	case roll < p.FetchTimeout+p.FetchRateLimit:
		fetchRateLimited.Add(1)
		w.Header().Set("Retry-After", "2")
		writeJSON(w, http.StatusTooManyRequests, map[string]any{"status": "error", "error": "simulated marketplace rate limit"})
		return
	case roll < p.FetchTimeout+p.FetchRateLimit+p.FetchError:
		fetchErrors.Add(1)
		writeJSON(w, http.StatusServiceUnavailable, map[string]any{"status": "error", "error": "simulated marketplace failure"})
		return
	}

	externalID := strings.TrimSpace(req.ExternalID)
	if externalID == "" {
		externalID = productIDFromURL(req.Marketplace, req.URL)
	}
	basePrice := 10_000 + int64(hashUint64(externalID)%490_000)
	state.mu.RLock()
	multiplier := state.PriceMultiplier
	version := state.PriceVersion
	state.mu.RUnlock()
	price := int64(math.Round(float64(basePrice) * multiplier))
	oldPrice := int64(math.Round(float64(basePrice) * maxFloat(multiplier+0.12, 1.05)))

	fetchSuccess.Add(1)
	writeJSON(w, http.StatusOK, map[string]any{
		"status": "success",
		"product": map[string]any{
			"external_id":             externalID,
			"title":                   fmt.Sprintf("Load Test %s Product %s", strings.ToUpper(req.Marketplace), externalID),
			"seller_name":             "Load Lab Seller",
			"brand":                   "Synthetic",
			"price_cents":             price,
			"old_price_cents":         oldPrice,
			"currency":                "RUB",
			"is_available":            true,
			"rating":                  4.5 + float64(hashUint64(externalID)%50)/100.0,
			"reviews_count":           100 + int(hashUint64(externalID)%9000),
			"load_test_price_version": version,
		},
	})
}

func rootHandler(w http.ResponseWriter, r *http.Request) {
	if strings.HasPrefix(r.URL.Path, "/bot") {
		handleTelegram(w, r)
		return
	}
	writeJSON(w, http.StatusNotFound, map[string]any{"error": "not found"})
}

func telegramDispatchHandler(w http.ResponseWriter, r *http.Request) {
	// Go ServeMux prefix matching does not match /botTOKEN by /bot/. The
	// root handler below is reached only if explicitly registered, so parse
	// the method from the final path component.
	handleTelegram(w, r)
}

func handleTelegram(w http.ResponseWriter, r *http.Request) {
	method := pathLast(r.URL.Path)
	p := currentProfile()
	sleepProfileLatency(p)
	roll := deterministicRoll(r.URL.Path + strconv.FormatUint(requestSequence.Add(1), 10))

	if roll < p.TelegramRateLimit {
		telegramRateLimited.Add(1)
		w.Header().Set("Retry-After", "2")
		writeJSON(w, http.StatusTooManyRequests, map[string]any{
			"ok":          false,
			"error_code":  429,
			"description": "Too Many Requests: retry after 2",
			"parameters":  map[string]any{"retry_after": 2},
		})
		return
	}
	if roll < p.TelegramRateLimit+p.TelegramError {
		telegramErrors.Add(1)
		writeJSON(w, http.StatusServiceUnavailable, map[string]any{
			"ok":          false,
			"error_code":  503,
			"description": "simulated Telegram failure",
		})
		return
	}

	telegramSuccess.Add(1)
	switch method {
	case "getUpdates":
		offset, _ := strconv.ParseInt(r.URL.Query().Get("offset"), 10, 64)
		timeoutSeconds, _ := strconv.Atoi(r.URL.Query().Get("timeout"))
		if timeoutSeconds < 0 {
			timeoutSeconds = 0
		}
		if timeoutSeconds > 30 {
			timeoutSeconds = 30
		}
		updates := telegramUpdates.poll(
			r.Context(),
			offset,
			time.Duration(timeoutSeconds)*time.Second,
		)
		telegramUpdatesDelivered.Add(uint64(len(updates)))
		writeJSON(w, http.StatusOK, map[string]any{"ok": true, "result": updates})
	case "deleteWebhook":
		telegramUpdates.reset()
		writeJSON(w, http.StatusOK, map[string]any{"ok": true, "result": true})
	case "setMyCommands", "answerCallbackQuery":
		writeJSON(w, http.StatusOK, map[string]any{"ok": true, "result": true})
	case "sendMessage", "editMessageText":
		var req telegramRequest
		_ = json.NewDecoder(r.Body).Decode(&req)
		if method == "sendMessage" {
			recordTelegramReply(req)
		}
		writeJSON(w, http.StatusOK, map[string]any{
			"ok": true,
			"result": map[string]any{
				"message_id": requestSequence.Add(1),
				"chat":       map[string]any{"id": req.ChatID},
				"text":       req.Text,
				"date":       time.Now().Unix(),
			},
		})
	default:
		writeJSON(w, http.StatusOK, map[string]any{"ok": true, "result": true})
	}
}

func stateHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	state.mu.RLock()
	currentProfile := state.Profile
	priceMultiplier := state.PriceMultiplier
	priceVersion := state.PriceVersion
	startedAt := state.StartedAt
	lastPriceShockAt := state.LastPriceShockAt
	state.mu.RUnlock()
	writeJSON(w, http.StatusOK, map[string]any{
		"profile":                           currentProfile,
		"price_multiplier":                  priceMultiplier,
		"price_version":                     priceVersion,
		"started_at":                        startedAt,
		"last_price_shock_at":               lastPriceShockAt,
		"telegram_update_queue_depth":       telegramUpdates.depth(),
		"telegram_updates_queued_total":     telegramUpdatesQueued.Load(),
		"telegram_updates_delivered_total":  telegramUpdatesDelivered.Load(),
		"telegram_duplicate_messages_total": telegramDuplicateMessages.Load(),
	})
}

func resetHandler(w http.ResponseWriter, r *http.Request) {
	if !authorizeControl(w, r) {
		return
	}
	state.mu.Lock()
	state.Profile = profiles["normal"]
	state.PriceMultiplier = 1.0
	state.PriceVersion = 0
	state.LastPriceShockAt = nil
	state.mu.Unlock()
	resetCounters()
	telegramUpdates.reset()
	resetTelegramReplies()
	writeJSON(w, http.StatusOK, map[string]any{"status": "reset"})
}

func profileHandler(w http.ResponseWriter, r *http.Request) {
	if !authorizeControl(w, r) {
		return
	}
	name := strings.TrimSpace(r.URL.Query().Get("name"))
	if name == "" {
		var payload struct {
			Name string `json:"name"`
		}
		_ = json.NewDecoder(r.Body).Decode(&payload)
		name = strings.TrimSpace(payload.Name)
	}
	selected, ok := profiles[name]
	if !ok {
		writeJSON(w, http.StatusBadRequest, map[string]any{
			"error":     "unknown profile",
			"available": sortedProfileNames(),
		})
		return
	}
	state.mu.Lock()
	state.Profile = selected
	state.mu.Unlock()
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "profile": selected})
}

func priceShockHandler(w http.ResponseWriter, r *http.Request) {
	if !authorizeControl(w, r) {
		return
	}
	percent, err := strconv.ParseFloat(r.URL.Query().Get("percent"), 64)
	if err != nil {
		var payload struct {
			Percent float64 `json:"percent"`
		}
		if decodeErr := json.NewDecoder(r.Body).Decode(&payload); decodeErr != nil {
			writeJSON(w, http.StatusBadRequest, map[string]any{"error": "percent is required"})
			return
		}
		percent = payload.Percent
	}
	if percent <= -95 || percent > 500 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "percent must be in (-95, 500]"})
		return
	}
	now := time.Now().UTC()
	state.mu.Lock()
	state.PriceMultiplier *= 1 + percent/100
	state.PriceVersion++
	state.LastPriceShockAt = &now
	multiplier := state.PriceMultiplier
	version := state.PriceVersion
	state.mu.Unlock()
	writeJSON(w, http.StatusOK, map[string]any{
		"status": "ok", "percent": percent,
		"price_multiplier": multiplier, "price_version": version,
	})
}

func telegramUpdatesHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	if !authorizeControl(w, r) {
		return
	}

	var payload struct {
		Updates []telegramUpdateInput `json:"updates"`
		ChatID  any                   `json:"chat_id"`
		Text    string                `json:"text"`
	}
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "invalid JSON"})
		return
	}
	updates := payload.Updates
	if len(updates) == 0 && strings.TrimSpace(payload.Text) != "" {
		updates = []telegramUpdateInput{{ChatID: payload.ChatID, Text: payload.Text}}
	}
	if len(updates) == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "at least one update is required"})
		return
	}

	queued := 0
	for _, update := range updates {
		if strings.TrimSpace(fmt.Sprint(update.ChatID)) == "" || strings.TrimSpace(update.Text) == "" {
			continue
		}
		telegramUpdates.enqueue(update.ChatID, update.Text)
		telegramUpdatesQueued.Add(1)
		queued++
	}
	if queued == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "all updates were invalid"})
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{
		"status":      "queued",
		"queued":      queued,
		"queue_depth": telegramUpdates.depth(),
	})
}

func grafanaAlertHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]any{"error": "method not allowed"})
		return
	}
	grafanaAlerts.Add(1)
	var payload any
	_ = json.NewDecoder(r.Body).Decode(&payload)
	log.Printf("received Grafana load-lab alert: %v", payload)
	writeJSON(w, http.StatusOK, map[string]any{"status": "accepted"})
}

func metricsHandler(w http.ResponseWriter, _ *http.Request) {
	p := currentProfile()
	requests := totalRequests.Load()
	average := 0.0
	if requests > 0 {
		average = float64(totalLatencyMicros.Load()) / float64(requests) / 1_000_000
	}
	state.mu.RLock()
	multiplier := state.PriceMultiplier
	version := state.PriceVersion
	state.mu.RUnlock()

	w.Header().Set("Content-Type", "text/plain; version=0.0.4")
	fmt.Fprintf(w, "# HELP load_simulator_up Whether the simulator is running.\n# TYPE load_simulator_up gauge\nload_simulator_up 1\n")
	fmt.Fprintf(w, "# HELP load_simulator_active_requests Current in-flight requests.\n# TYPE load_simulator_active_requests gauge\nload_simulator_active_requests %d\n", activeRequests.Load())
	fmt.Fprintf(w, "# HELP load_simulator_fetch_requests_total Simulated fetch requests.\n# TYPE load_simulator_fetch_requests_total counter\n")
	fmt.Fprintf(w, "load_simulator_fetch_requests_total{result=\"success\"} %d\n", fetchSuccess.Load())
	fmt.Fprintf(w, "load_simulator_fetch_requests_total{result=\"error\"} %d\n", fetchErrors.Load())
	fmt.Fprintf(w, "load_simulator_fetch_requests_total{result=\"rate_limited\"} %d\n", fetchRateLimited.Load())
	fmt.Fprintf(w, "load_simulator_fetch_requests_total{result=\"timeout\"} %d\n", fetchTimeouts.Load())
	fmt.Fprintf(w, "# HELP load_simulator_telegram_requests_total Simulated Telegram requests.\n# TYPE load_simulator_telegram_requests_total counter\n")
	fmt.Fprintf(w, "load_simulator_telegram_requests_total{result=\"success\"} %d\n", telegramSuccess.Load())
	fmt.Fprintf(w, "load_simulator_telegram_requests_total{result=\"error\"} %d\n", telegramErrors.Load())
	fmt.Fprintf(w, "load_simulator_telegram_requests_total{result=\"rate_limited\"} %d\n", telegramRateLimited.Load())
	fmt.Fprintf(w, "# HELP load_simulator_grafana_alerts_total Grafana alerts captured by the lab.\n# TYPE load_simulator_grafana_alerts_total counter\nload_simulator_grafana_alerts_total %d\n", grafanaAlerts.Load())
	fmt.Fprintf(w, "# HELP load_simulator_telegram_updates_total Synthetic Telegram updates.\n# TYPE load_simulator_telegram_updates_total counter\n")
	fmt.Fprintf(w, "load_simulator_telegram_updates_total{result=\"queued\"} %d\n", telegramUpdatesQueued.Load())
	fmt.Fprintf(w, "load_simulator_telegram_updates_total{result=\"delivered\"} %d\n", telegramUpdatesDelivered.Load())
	fmt.Fprintf(w, "# HELP load_simulator_telegram_update_queue_depth Pending synthetic Telegram updates.\n# TYPE load_simulator_telegram_update_queue_depth gauge\nload_simulator_telegram_update_queue_depth %d\n", telegramUpdates.depth())
	fmt.Fprintf(w, "# HELP load_simulator_telegram_duplicate_messages_total Telegram replies repeated for the same chat and text within five seconds.\n# TYPE load_simulator_telegram_duplicate_messages_total counter\nload_simulator_telegram_duplicate_messages_total %d\n", telegramDuplicateMessages.Load())
	fmt.Fprintf(w, "# HELP load_simulator_average_request_duration_seconds Approximate average request duration.\n# TYPE load_simulator_average_request_duration_seconds gauge\nload_simulator_average_request_duration_seconds %.6f\n", average)
	fmt.Fprintf(w, "# HELP load_simulator_price_multiplier Current synthetic price multiplier.\n# TYPE load_simulator_price_multiplier gauge\nload_simulator_price_multiplier %.6f\n", multiplier)
	fmt.Fprintf(w, "# HELP load_simulator_price_version Current synthetic price version.\n# TYPE load_simulator_price_version gauge\nload_simulator_price_version %d\n", version)
	for name := range profiles {
		value := 0
		if name == p.Name {
			value = 1
		}
		fmt.Fprintf(w, "load_simulator_profile{profile=\"%s\"} %d\n", name, value)
	}
}

func authorizeControl(w http.ResponseWriter, r *http.Request) bool {
	expected := envOr("LOAD_SIMULATOR_CONTROL_KEY", "load-lab-control-key")
	supplied := r.Header.Get("X-Load-Control-Key")
	if supplied == "" {
		supplied = r.URL.Query().Get("key")
	}
	if supplied != expected {
		writeJSON(w, http.StatusUnauthorized, map[string]any{"error": "invalid control key"})
		return false
	}
	return true
}

func currentProfile() profile {
	state.mu.RLock()
	defer state.mu.RUnlock()
	return state.Profile
}

func sleepProfileLatency(p profile) {
	if p.MaxLatencyMS <= 0 {
		return
	}
	minLatency := maxInt(p.MinLatencyMS, 0)
	maxLatency := maxInt(p.MaxLatencyMS, minLatency)
	delta := maxLatency - minLatency
	latency := minLatency
	if delta > 0 {
		latency += rand.Intn(delta + 1)
	}
	time.Sleep(time.Duration(latency) * time.Millisecond)
}

func deterministicRoll(value string) float64 {
	return float64(hashUint64(value)%1_000_000) / 1_000_000.0
}

func hashUint64(value string) uint64 {
	sum := sha256.Sum256([]byte(value))
	return binary.BigEndian.Uint64(sum[:8])
}

func productIDFromURL(marketplace, value string) string {
	return fmt.Sprintf("lt-%s-%012d", marketplace, hashUint64(value)%1_000_000_000_000)
}

func pathLast(value string) string {
	value = strings.Trim(value, "/")
	if value == "" {
		return ""
	}
	parts := strings.Split(value, "/")
	return parts[len(parts)-1]
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func envOr(name, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(name)); value != "" {
		return value
	}
	return fallback
}

func envDuration(name string, fallback time.Duration) time.Duration {
	value := strings.TrimSpace(os.Getenv(name))
	if value == "" {
		return fallback
	}
	parsed, err := time.ParseDuration(value)
	if err != nil {
		return fallback
	}
	return parsed
}

func resetCounters() {
	fetchSuccess.Store(0)
	fetchErrors.Store(0)
	fetchRateLimited.Store(0)
	fetchTimeouts.Store(0)
	telegramSuccess.Store(0)
	telegramErrors.Store(0)
	telegramRateLimited.Store(0)
	grafanaAlerts.Store(0)
	telegramUpdatesQueued.Store(0)
	telegramUpdatesDelivered.Store(0)
	telegramDuplicateMessages.Store(0)
	totalRequests.Store(0)
	totalLatencyMicros.Store(0)
}

func (q *telegramUpdateQueue) enqueue(chatID any, text string) {
	q.mu.Lock()
	defer q.mu.Unlock()
	updateID := q.nextID
	q.nextID++
	messageID := requestSequence.Add(1)
	q.updates = append(q.updates, map[string]any{
		"update_id": updateID,
		"message": map[string]any{
			"message_id": messageID,
			"date":       time.Now().Unix(),
			"chat":       map[string]any{"id": chatID, "type": "private"},
			"from":       map[string]any{"id": chatID, "is_bot": false, "first_name": "Load Test"},
			"text":       text,
		},
	})
	close(q.notify)
	q.notify = make(chan struct{})
}

func (q *telegramUpdateQueue) poll(ctx context.Context, offset int64, timeout time.Duration) []map[string]any {
	for {
		q.mu.Lock()
		q.pruneLocked(offset)
		if len(q.updates) > 0 {
			batchSize := len(q.updates)
			if batchSize > 100 {
				batchSize = 100
			}
			result := append([]map[string]any(nil), q.updates[:batchSize]...)
			q.mu.Unlock()
			return result
		}
		notify := q.notify
		q.mu.Unlock()
		if timeout <= 0 {
			return []map[string]any{}
		}
		timer := time.NewTimer(timeout)
		select {
		case <-ctx.Done():
			if !timer.Stop() {
				<-timer.C
			}
			return []map[string]any{}
		case <-notify:
			if !timer.Stop() {
				<-timer.C
			}
			continue
		case <-timer.C:
			return []map[string]any{}
		}
	}
}

func (q *telegramUpdateQueue) pruneLocked(offset int64) {
	if offset <= 0 || len(q.updates) == 0 {
		return
	}
	firstKept := 0
	for firstKept < len(q.updates) {
		value, _ := q.updates[firstKept]["update_id"].(int64)
		if value >= offset {
			break
		}
		firstKept++
	}
	if firstKept > 0 {
		q.updates = append([]map[string]any(nil), q.updates[firstKept:]...)
	}
}

func (q *telegramUpdateQueue) depth() int {
	q.mu.Lock()
	defer q.mu.Unlock()
	return len(q.updates)
}

func (q *telegramUpdateQueue) reset() {
	q.mu.Lock()
	defer q.mu.Unlock()
	q.updates = nil
	q.nextID = 1
	close(q.notify)
	q.notify = make(chan struct{})
}

func recordTelegramReply(req telegramRequest) {
	key := fmt.Sprintf("%v\x00%s", req.ChatID, req.Text)
	now := time.Now()
	telegramReplies.mu.Lock()
	if previous, ok := telegramReplies.seen[key]; ok && now.Sub(previous) <= 5*time.Second {
		telegramDuplicateMessages.Add(1)
	}
	telegramReplies.seen[key] = now
	telegramReplies.mu.Unlock()
}

func resetTelegramReplies() {
	telegramReplies.mu.Lock()
	telegramReplies.seen = make(map[string]time.Time)
	telegramReplies.mu.Unlock()
}

func sortedProfileNames() []string {
	names := []string{"fast", "normal", "realistic", "slow", "degraded", "outage", "antibot", "telegram_429"}
	return names
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}
func maxFloat(a, b float64) float64 {
	if a > b {
		return a
	}
	return b
}
