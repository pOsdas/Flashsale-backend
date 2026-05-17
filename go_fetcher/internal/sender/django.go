package sender

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"go_fetcher/internal/models"
	"io"
	"net/http"
	"strings"
	"time"
)

type DjangoSender struct {
	baseURL    string
	apiKey     string
	httpClient *http.Client
}

type ImportPayload struct {
	Source  string                 `json:"source"`
	BatchID string                 `json:"batch_id"`
	Items   []models.ProductImport `json:"items"`
}

type ImportResponse struct {
	Success bool   `json:"success"`
	Status  string `json:"status"`
	Source  string `json:"source"`
	BatchID string `json:"batch_id"`
	Created int    `json:"created"`
	Updated int    `json:"updated"`
	Error   string `json:"error"`
}

func NewDjangoSender(baseURL string, apiKey string) *DjangoSender {
	return &DjangoSender{
		baseURL: strings.TrimRight(baseURL, "/"),
		apiKey:  apiKey,
		httpClient: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
}

func (s *DjangoSender) ImportProducts(
	ctx context.Context,
	payload ImportPayload,
) (ImportResponse, error) {
	requestBody, err := json.Marshal(payload)
	if err != nil {
		return ImportResponse{}, fmt.Errorf("failed to encode import payload: %w", err)
	}

	requestURL := s.baseURL + "/api/v1/fetcher/import"

	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		requestURL,
		bytes.NewReader(requestBody),
	)
	if err != nil {
		return ImportResponse{}, fmt.Errorf("failed to create django request: %w", err)
	}

	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Accept", "application/json")
	request.Header.Set("X-Fetcher-Api-Key", s.apiKey)

	response, err := s.httpClient.Do(request)
	if err != nil {
		return ImportResponse{}, fmt.Errorf("failed to send import request to django: %w", err)
	}
	defer response.Body.Close()

	responseBody, err := io.ReadAll(response.Body)
	if err != nil {
		return ImportResponse{}, fmt.Errorf("failed to read django response body: %w", err)
	}

	var importResponse ImportResponse

	if err := json.Unmarshal(responseBody, &importResponse); err != nil {
		return ImportResponse{}, fmt.Errorf(
			"failed to decode django response: %w, body: %s",
			err,
			string(responseBody),
		)
	}

	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return importResponse, fmt.Errorf(
			"django import failed with status %d: %s",
			response.StatusCode,
			string(responseBody),
		)
	}

	return importResponse, nil
}
