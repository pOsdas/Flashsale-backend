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
