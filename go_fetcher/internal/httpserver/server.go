package httpserver

import (
	"context"
	"log/slog"
	"net/http"
	"time"
)

type ProductFetcher func(ctx context.Context, req FetchProductRequest) (*ProductDTO, error)

type Server struct {
	addr        string
	apiKey      string
	logger      *slog.Logger
	wbFetcher   ProductFetcher
	ozonFetcher ProductFetcher
}

func NewServer(
	addr string,
	apiKey string,
	logger *slog.Logger,
	wbFetcher ProductFetcher,
	ozonFetcher ProductFetcher,
) *Server {
	return &Server{
		addr:        addr,
		apiKey:      apiKey,
		logger:      logger,
		wbFetcher:   wbFetcher,
		ozonFetcher: ozonFetcher,
	}
}

func (s *Server) Run(ctx context.Context) error {
	mux := http.NewServeMux()

	mux.HandleFunc("/api/v1/fetch/product/", s.handleFetchProduct)

	httpServer := &http.Server{
		Addr:              s.addr,
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       20 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	errCh := make(chan error, 1)

	go func() {
		s.logger.Info("go_fetcher http server started", "addr", s.addr)

		s.logger.Info(
			"GO_FETCHER_HTTP_SERVER_LISTENING",
			slog.String("addr", s.addr),
		)

		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			errCh <- err
			return
		}

		errCh <- nil
	}()

	select {
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		s.logger.Info("go_fetcher http server shutting down")

		if err := httpServer.Shutdown(shutdownCtx); err != nil {
			return err
		}

		return nil

	case err := <-errCh:
		return err
	}
}
