# Important

Wildberries uses the regular Go HTTP parser first and can fall back to a real
Chromium session when WB returns 403, 498, or an antibot response:

Local:
```shell
WB_BROWSER_FETCHER_ENABLED=true
WB_BROWSER_FETCHER_URL=http://127.0.0.1:8096
WB_BROWSER_FETCHER_TIMEOUT_SECONDS=35
```

Docker:
```shell
WB_BROWSER_FETCHER_ENABLED=true
WB_BROWSER_FETCHER_URL=http://wb_browser_fetcher:8096
WB_BROWSER_FETCHER_TIMEOUT_SECONDS=35
```

The WB browser fetcher uses `secrets/wb_cookie.txt` and exposes health at
`GET /api/v1/health` on port `8096`.

Ozon parser may return 403 Antibot Challenge when running inside Docker.
For Ozon, we have a fallback scenario with Playwright parser:

Local:
```shell
OZON_BROWSER_FETCHER_ENABLED=true
OZON_BROWSER_FETCHER_URL=http://127.0.0.1:8095
OZON_HTTP_PARSER_TIMEOUT_SECONDS=12
OZON_BROWSER_FETCHER_TIMEOUT_SECONDS=35
```

Docker:
```shell
OZON_BROWSER_FETCHER_ENABLED=true
OZON_BROWSER_FETCHER_URL=http://ozon_browser_fetcher:8095
OZON_HTTP_PARSER_TIMEOUT_SECONDS=12
OZON_BROWSER_FETCHER_TIMEOUT_SECONDS=35
```

Cookies are stored in the secrets folder:
- secrets/wb_cookie.txt
- secrets/ozon_cookie.txt

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

## Playwright for cookies update
> cd backend
```shell
poetry run python ..\go_fetcher\tools\playwright\update_marketplace_cookie.py --marketplace wb
```
```shell
poetry run python ..\go_fetcher\tools\playwright\update_marketplace_cookie.py --marketplace ozon
```
