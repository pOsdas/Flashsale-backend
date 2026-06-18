[⬅️ К основному README](../README.MD)

# Обновление cookies

Краткая инструкция по обновлению cookies для WB и Ozon, которые используются `go_fetcher` и Ozon Playwright fallback.

## 1. Где лежат cookies

Файлы cookies должны лежать здесь:

```text
go_fetcher/secrets/wb_cookie.txt
go_fetcher/secrets/ozon_cookie.txt
```

Папка `secrets` подключается в контейнеры как read-only volume:

```text
./go_fetcher/secrets:/app/secrets:ro
```

## 2. Обновить или создать cookies через Playwright-скрипт

```bash
mkdir -p go_fetcher/secrets
```

Скрипт обновления cookies находится в tools: `tools/playwright/update_marketplace_cookie.py`

```shell
cd backend
```
```shell
poetry run python ..\go_fetcher\tools\playwright\update_marketplace_cookie.py --marketplace wb
```
```shell
poetry run python ..\go_fetcher\tools\playwright\update_marketplace_cookie.py --marketplace ozon
```

После выполнения cookies должны быть сохранены в:

```text
go_fetcher/secrets/wb_cookie.txt
go_fetcher/secrets/ozon_cookie.txt
```

## 3. Перезапустить fetcher после обновления cookies

Так как cookies подключены в контейнер как volume, обычно достаточно перезапустить fetcher-сервисы:

```bash
docker compose restart go_fetcher ozon_browser_fetcher
```

После этого можно проверить логи:

```bash
docker compose logs -f go_fetcher
```

```bash
docker compose logs -f ozon_browser_fetcher
```

## 4. Проверить parser-health

После обновления cookies выполни:

```bash
curl -X GET "http://127.0.0.1:8090/api/v1/parser/health"
```

Если всё работает нормально, статус должен быть:

```text
ok
```

Если часть проверок не проходит, возможен статус:

```text
degraded
```

Это может означать, что marketplace временно ограничил запросы, cookies устарели или включилась antibot-защита.

## Следующие документы

- [Локальный запуск](01-local-run.md)
- [Проверка parser-health](03-parser-health.md)
- [Demo-сценарий](04-demo-scenario.md)

---

[⬅️ К основному README](../README.MD)