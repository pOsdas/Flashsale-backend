package main

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/joho/godotenv"

	"go_fetcher/internal/config"
	"go_fetcher/internal/parsers/wildberries"
	"go_fetcher/internal/pipeline"
	"go_fetcher/internal/sender"
)

func main() {
	if err := godotenv.Load(); err != nil {
		log.Println("No .env file found")
	}

	cfg, err := config.Load()
	if err != nil {
		log.Fatal(err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	wbParser := wildberries.NewParser()

	djangoSender := sender.NewDjangoSender(
		cfg.DjangoURL,
		cfg.FetcherAPIKey,
	)

	importPipeline := pipeline.NewImportPipeline(
		wbParser,
		djangoSender,
		"wildberries",
	)

	response, err := importPipeline.RunProductImport(
		ctx,
		"302421341",
	)
	if err != nil {
		log.Fatal(err)
	}

	fmt.Printf("Django import success: %t\n", response.Success)
	fmt.Printf("Django import status: %s\n", response.Status)
	fmt.Printf("Created: %d\n", response.Created)
	fmt.Printf("Updated: %d\n", response.Updated)
}
