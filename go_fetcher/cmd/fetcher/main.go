package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/joho/godotenv"

	"go_fetcher/internal/models"
	"go_fetcher/internal/parsers/wildberries"
	"go_fetcher/internal/sender"
)

func main() {
	if err := godotenv.Load(); err != nil {
		log.Println("No .env file found")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	parser := wildberries.NewParser()

	product, err := parser.ParseProduct(ctx, "302421341")
	if err != nil {
		log.Fatal(err)
	}

	fmt.Printf("SKU: %s\n", product.SKU)
	fmt.Printf("Title: %s\n", product.Title)
	fmt.Printf("PriceCents: %d\n", product.PriceCents)
	fmt.Printf("Currency: %s\n", product.Currency)
	fmt.Printf("Available: %d\n", product.Available)
	fmt.Printf("IsActive: %t\n", product.IsActive)

	djangoURL := os.Getenv("DJANGO_URL")
	if djangoURL == "" {
		log.Fatal("$DJANGO_URL is required")
	}

	fetcherAPIKey := os.Getenv("FETCHER_API_KEY")
	if fetcherAPIKey == "" {
		log.Fatal("FETCHER_API_KEY is required")
	}

	djangoSender := sender.NewDjangoSender(
		djangoURL,
		fetcherAPIKey,
	)

	payload := sender.ImportPayload{
		Source:  "wildberries",
		BatchID: fmt.Sprintf("wb-%s-%d", product.SKU, time.Now().Unix()),
		Items: []models.ProductImport{
			product.ToImport(),
		},
	}

	importResponse, err := djangoSender.SendImport(ctx, payload)
	if err != nil {
		log.Fatal(err)
	}

	fmt.Printf("Django import success: %t\n", importResponse.Success)
	fmt.Printf("Django import status: %s\n", importResponse.Status)
	fmt.Printf("Created: %d\n", importResponse.Created)
	fmt.Printf("Updated: %d\n", importResponse.Updated)
}
