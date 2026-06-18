[⬅️ К основному README](../README.MD)

# Проверка parser-health

Parser Health позволяет быстро проверить работоспособность парсеров Wildberries и Ozon

Проверка выполняется через `go_fetcher`.

## Что проверяется

Для каждого маркетплейса система выполняет несколько шагов:

1. Поиск товара.
2. Выбор найденного товара.
3. Получение карточки товара.
4. Проверка основных данных:
   - SKU;
   - название;
   - цена;
   - доступность.

Также проверяется:

- наличие cookies;
- ответы маркетплейса;
- признаки antibot-защиты;
- ошибки доступа;
- ошибки rate limiting.

## Запуск проверки

```bash
curl -X GET "http://127.0.0.1:8090/api/v1/parser/health"
```

Пример ответа:

```json
{
  "status": "ok",
  "checks": [...]
}
```

## Дополнительные проверки

Проверить состояние Ozon Playwright fallback:

```bash
curl -X GET "http://127.0.0.1:8095/api/v1/health"
```

Посмотреть логи fetcher:

```bash
docker compose logs -f go_fetcher
```

Посмотреть логи fallback:

```bash
docker compose logs -f ozon_browser_fetcher
```

## Когда parser-health считается успешным

Проверку можно считать успешной если:

- endpoint отвечает;
- возвращается корректный JSON;
- parser-health показывает `ok` либо понятный `degraded`;
- отсутствуют ошибки `cookie_present=false`;
- fetcher способен получать данные хотя бы по одному сценарию проверки.

## Следующие документы

- [Локальный запуск](01-local-run.md)
- [Обновление cookies](02-cookies-refresh.md)
- [Demo-сценарий](04-demo-scenario.md)

---

[⬅️ К основному README](../README.MD)