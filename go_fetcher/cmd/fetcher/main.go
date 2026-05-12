package main

import (
	"context"
	"fmt"
	"log"
	"time"

	"go_fetcher/internal/parsers/wildberries"

	"github.com/joho/godotenv"
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
}
