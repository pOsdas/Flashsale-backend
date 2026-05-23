# Important

Ozon parser may return 403 Antibot Challenge when running inside Docker.
For Ozon, use local execution with a valid OZON_COOKIE.

# Commands

## WB Commands:
1. Search
```shell
go run ./cmd/fetcher wb search --limit=100 "<query>"
```
For example:
```shell
go run ./cmd/fetcher wb search --limit=100 "iphone"
```

2. Category
```shell
go run ./cmd/fetcher wb category --limit=100 "<category_name>"
```
For example:
```shell
go run ./cmd/fetcher wb category --limit=100 "кошельки и кредитницы"
```

3. By id
```shell
go run ./cmd/fetcher wb product "<id>"
```
For example:
```shell
go run ./cmd/fetcher wb product "302421341"
```

## Ozon Commands:
1. Search
```shell
go run ./cmd/fetcher ozon search --limit=100 "<query>"
```
For example:
```shell
go run ./cmd/fetcher ozon search --limit=100 "iphone"
```

2. Category
```shell
go run ./cmd/fetcher ozon category --limit=100 "<category_url>"
```
For example:
```shell
go run ./cmd/fetcher ozon category --limit=100 "https://www.ozon.ru/category/svitery-dzhempery-i-kardigany-muzhskie-7554/"
```

> How to get category url?
```shell
go run ./cmd/fetcher ozon categories --limit=10 "мужские свитеры"
```

3. By url
```shell
go run ./cmd/fetcher ozon product "<url>"
```
For example:
```shell
go run ./cmd/fetcher ozon product "/product/sirop-topping-bez-sahara-nizkokaloriynyy-mr-djemius-zero-solenaya-karamel-330g-1919933573/"
```

## Docker commands:
For example:
```shell
docker run --rm --env-file .env-docker go_fetcher ozon search --limit=10 "iphone"
```
```shell
docker run --rm --env-file .env-docker go_fetcher wb search --limit=10 "iphone"
```
