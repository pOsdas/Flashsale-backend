package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
)

func TestFetchProductSuccess(t *testing.T) {
	resetCounters()
	state.mu.Lock()
	state.Profile = profiles["fast"]
	state.PriceMultiplier = 1
	state.PriceVersion = 0
	state.mu.Unlock()

	payload := []byte(`{"marketplace":"wb","url":"https://www.wildberries.ru/catalog/1/detail.aspx","external_id":"lt-wb-1"}`)
	request := httptest.NewRequest(http.MethodPost, "/api/v1/fetch/product/", bytes.NewReader(payload))
	response := httptest.NewRecorder()

	fetchHandler(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", response.Code, response.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body["status"] != "success" {
		t.Fatalf("unexpected status: %#v", body)
	}
}

func TestPriceShockChangesPriceVersion(t *testing.T) {
	t.Setenv("LOAD_SIMULATOR_CONTROL_KEY", "test-control")
	state.mu.Lock()
	state.PriceMultiplier = 1
	state.PriceVersion = 0
	state.mu.Unlock()

	request := httptest.NewRequest(http.MethodPost, "/__control/price-shock?percent=-15", nil)
	request.Header.Set("X-Load-Control-Key", "test-control")
	response := httptest.NewRecorder()

	priceShockHandler(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.Code)
	}
	state.mu.RLock()
	defer state.mu.RUnlock()
	if state.PriceVersion != 1 {
		t.Fatalf("expected version 1, got %d", state.PriceVersion)
	}
	if state.PriceMultiplier >= 1 {
		t.Fatalf("expected lower multiplier, got %f", state.PriceMultiplier)
	}
}

func TestTelegramSendMessage(t *testing.T) {
	state.mu.Lock()
	state.Profile = profiles["fast"]
	state.mu.Unlock()

	request := httptest.NewRequest(http.MethodPost, "/bottest-token/sendMessage", bytes.NewReader([]byte(`{"chat_id":"load-1","text":"hello"}`)))
	response := httptest.NewRecorder()

	rootHandler(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.Code)
	}
	if !bytes.Contains(response.Body.Bytes(), []byte(`"ok":true`)) {
		t.Fatalf("unexpected Telegram response: %s", response.Body.String())
	}
}

func TestControlRequiresKey(t *testing.T) {
	_ = os.Setenv("LOAD_SIMULATOR_CONTROL_KEY", "required")
	t.Cleanup(func() { _ = os.Unsetenv("LOAD_SIMULATOR_CONTROL_KEY") })
	request := httptest.NewRequest(http.MethodPost, "/__control/reset", nil)
	response := httptest.NewRecorder()

	resetHandler(response, request)

	if response.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", response.Code)
	}
}

func TestTelegramUpdatesQueueAndPoll(t *testing.T) {
	t.Setenv("LOAD_SIMULATOR_CONTROL_KEY", "test-control")
	telegramUpdates.reset()
	resetCounters()

	payload := []byte(`{"updates":[{"chat_id":"load-1","text":"/products"},{"chat_id":"load-2","text":"/help"}]}`)
	request := httptest.NewRequest(http.MethodPost, "/__control/telegram-updates", bytes.NewReader(payload))
	request.Header.Set("X-Load-Control-Key", "test-control")
	response := httptest.NewRecorder()

	telegramUpdatesHandler(response, request)
	if response.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d: %s", response.Code, response.Body.String())
	}

	updates := telegramUpdates.poll(request.Context(), 0, 0)
	if len(updates) != 2 {
		t.Fatalf("expected 2 updates, got %d", len(updates))
	}
	if telegramUpdates.depth() != 2 {
		t.Fatalf("expected queue depth 2, got %d", telegramUpdates.depth())
	}

	updates = telegramUpdates.poll(request.Context(), 3, 0)
	if len(updates) != 0 {
		t.Fatalf("expected queue to be pruned, got %d updates", len(updates))
	}
}

func TestTelegramDuplicateReplyMetric(t *testing.T) {
	resetTelegramReplies()
	telegramDuplicateMessages.Store(0)
	req := telegramRequest{ChatID: "load-1", Text: "same reply"}
	recordTelegramReply(req)
	recordTelegramReply(req)
	if telegramDuplicateMessages.Load() != 1 {
		t.Fatalf("expected one duplicate, got %d", telegramDuplicateMessages.Load())
	}
}

func TestTelegramGetUpdatesThroughHTTPRouter(t *testing.T) {
	state.mu.Lock()
	state.Profile = profiles["fast"]
	state.mu.Unlock()
	telegramUpdates.reset()
	telegramUpdates.enqueue("load-1", "/products")

	server := httptest.NewServer(newHandler())
	defer server.Close()

	response, err := http.Get(server.URL + "/botload-lab-token/getUpdates?timeout=0")
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()

	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.StatusCode)
	}

	var body struct {
		OK     bool             `json:"ok"`
		Result []map[string]any `json:"result"`
	}
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if !body.OK || len(body.Result) != 1 {
		t.Fatalf("unexpected response: %#v", body)
	}
}
