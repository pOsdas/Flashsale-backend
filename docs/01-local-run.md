[⬅️ К основному README](../README.MD)

# Локальный запуск

Краткая инструкция по запуску Flashsale Backend через Docker Compose.

Проект поднимает полный локальный контур:

- Django backend;
- PostgreSQL;
- Redis;
- RabbitMQ;
- Go fetcher;
- Ozon Playwright fallback;
- monitoring scanner;
- outbox worker;
- notification consumer;
- Telegram onboarding bot;
- Prometheus;
- Grafana;
- Loki;
- Promtail.

## 1. Проверить env-файлы

Перед запуском должны существовать файлы:

```text
backend/.env.docker
go_fetcher/.env
```

Также желательно проверить наличие cookies:

```text
go_fetcher/secrets/wb_cookie.txt
go_fetcher/secrets/ozon_cookie.txt
```

Если cookies отсутствуют или устарели, проект всё равно может запуститься, но parser-health может вернуть `degraded`.

Инструкция по обновлению cookies:

[docs/02-cookies-refresh.md](02-cookies-refresh.md)

## 2. Запустить проект

Из корня проекта:

```bash
docker compose up --build
```

Запуск в фоне:

```bash
docker compose up --build -d
```

## 3. Проверить контейнеры

```bash
docker compose ps
```

Основные контейнеры должны быть в состоянии `running` или `healthy`.

Особенно важно проверить:

```text
flashsale_backend
flashsale_go_fetcher
flashsale_ozon_browser_fetcher
flashsale_monitoring_scanner
flashsale_outbox_worker
flashsale_notification_consumer
flashsale_rabbitmq
flashsale_prometheus
flashsale_grafana
flashsale_loki
```

## 4. Проверить backend

Backend доступен по адресу:

```text
http://127.0.0.1:8000
```

Django admin:

```text
http://127.0.0.1:8000/admin/
```

## 5. Проверить go_fetcher и parser-health

Parser-health:

```bash
curl -X GET "http://127.0.0.1:8090/api/v1/parser/health"
```

Возможные статусы:

```text
ok
degraded
error
```

`degraded` означает, что WB или Ozon временно ограничили запросы, cookies устарели или marketplace вернул antibot-ответ.

Подробная инструкция:

```text
docs/03-parser-health.md
```

## 6. Проверить Ozon Playwright fallback

Health endpoint:

```bash
curl -X GET "http://127.0.0.1:8095/api/v1/health"
```

Этот сервис используется как fallback для Ozon, если обычный fetcher не может получить данные напрямую.

## 7. Проверить RabbitMQ

RabbitMQ Management UI:

```text
http://127.0.0.1:15672
```

RabbitMQ используется для доставки событий от outbox worker к notification consumer.

## 8. Проверить Grafana и Prometheus

Prometheus:

```text
http://127.0.0.1:9090
```

Grafana:

```text
http://127.0.0.1:3000
```

Данные для входа в Grafana по умолчанию:

```text
admin
admin
```

Grafana используется для просмотра метрик, dashboards и логов через Loki.

## 9. Минимальная проверка после запуска

После запуска достаточно проверить:

```bash
docker compose ps
```

```bash
curl -X GET "http://127.0.0.1:8090/api/v1/parser/health"
```

```bash
curl -X GET "http://127.0.0.1:8095/api/v1/health"
```

И открыть:

```text
http://127.0.0.1:8000/admin/
http://127.0.0.1:15672
http://127.0.0.1:3000
```

Для MVP допустимо, если parser-health временно возвращает `degraded`, но причина понятна из ответа: cookies, antibot, rate limit или временная блокировка маркетплейса.

## Следующие документы

- [Обновление cookies](02-cookies-refresh.md)
- [Проверка parser-health](03-parser-health.md)
- [Demo-сценарий](04-demo-scenario.md)

---

[⬅️ К основному README](../README.MD)