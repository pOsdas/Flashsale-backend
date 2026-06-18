# Flashsale Backend

Backend-система для мониторинга товаров на маркетплейсах, отслеживания изменений цены, наличия, рейтинга и отзывов, а также отправки уведомлений пользователю при важных изменениях.

Проект построен как production-like backend: с отдельным сервисом парсинга, scanner worker, кэшированием данных товаров, outbox-паттерном, RabbitMQ, Telegram-уведомлениями, parser-health диагностикой, Prometheus, Grafana и централизованными логами через Loki.

## Что делает проект

Flashsale Backend позволяет пользователю добавлять товары для мониторинга и автоматически отслеживать изменения по ним.

Система умеет:

- получать данные о товарах с Wildberries и Ozon;
- использовать отдельный Go-сервис `go_fetcher` для парсинга маркетплейсов;
- использовать Playwright fallback для Ozon при необходимости браузерного получения данных;
- кэшировать состояние товара, чтобы не дергать маркетплейсы лишний раз;
- запускать фоновый scanner worker для регулярной проверки товаров;
- сохранять снимки состояния товара в `ProductSnapshot`;
- сравнивать новое состояние товара с предыдущим;
- создавать alert при изменении цены, наличия, рейтинга, отзывов или других важных параметров;
- отправлять события через outbox worker;
- доставлять события через RabbitMQ;
- обрабатывать события в notification consumer;
- отправлять Telegram-уведомления пользователю;
- хранить историю доставленных уведомлений;
- проверять состояние парсеров через parser-health;
- собирать метрики через Prometheus;
- отображать метрики и логи в Grafana;
- хранить централизованные логи через Loki и Promtail.
- имеет дополнительный GraphQL API-слой для части доменной логики, хотя основной рабочий сценарий сейчас построен вокруг REST API и фоновых workers;

## Основной пользовательский сценарий

1. Пользователь добавляет товар для мониторинга.
2. Backend сохраняет цель мониторинга в базе данных.
3. Scanner worker выбирает товары, которые пора проверить.
4. Product cache layer проверяет, есть ли свежие данные по товару.
5. Если свежего кэша нет, backend обращается к `go_fetcher`.
6. `go_fetcher` получает данные с WB или Ozon.
7. Для Ozon при необходимости используется Playwright fallback.
8. Backend сохраняет новый `ProductSnapshot`.
9. Система сравнивает новый snapshot с предыдущим.
10. Если найдено важное изменение, создается `Alert`.
11. Alert публикуется через outbox.
12. Outbox worker отправляет событие в RabbitMQ.
13. Notification consumer получает событие.
14. Notification service формирует текст уведомления.
15. Пользователь получает Telegram-уведомление.
16. История уведомлений доступна через API.

## Архитектура

Проект состоит из нескольких основных частей:

- `backend` — основной Django backend;
- `GraphQL API` — дополнительный API-слой, который был реализован для части операций, но сейчас не является основным интерфейсом MVP;
- `go_fetcher` — Go-сервис для получения данных с маркетплейсов;
- `ozon_browser_fetcher` — Playwright fallback для Ozon;
- `monitoring_scanner` — worker регулярной проверки товаров;
- `outbox_worker` — worker публикации событий из outbox;
- `notification_consumer` — consumer уведомлений из RabbitMQ;
- `telegram_onboarding_bot` — бот для подключения Telegram-канала пользователя;
- `postgres` — основная база данных;
- `redis` — кэш, блокировки и вспомогательная инфраструктура;
- `rabbitmq` — брокер событий;
- `prometheus` — сбор метрик;
- `grafana` — dashboards, метрики и алерты;
- `loki` — централизованное хранение логов;
- `promtail` — сбор логов из Docker-контейнеров.

## Основные модули backend

### Catalog

Отвечает за товары и данные каталога.

### Monitoring

Отвечает за мониторинг товаров:

- `MonitoringTarget`;
- `ProductSnapshot`;
- `Alert`;
- scanner worker;
- сравнение snapshot-ов;
- создание alert-ов;
- кэширование состояния товаров.

### Fetcher integration

Отвечает за интеграцию backend с `go_fetcher`.

Backend не парсит маркетплейсы напрямую. Он обращается к отдельному сервису, который отвечает за получение и нормализацию данных.

### GraphQL API

В проекте также есть GraphQL API-слой.

Он был реализован как дополнительный способ работы с частью доменной логики проекта. Сейчас основной пользовательский сценарий MVP построен вокруг REST API

### Outbox

Реализует outbox-паттерн для надежной публикации событий.

Это нужно, чтобы alert не потерялся между сохранением в базе и отправкой события в RabbitMQ.

### Notifications

Отвечает за доставку уведомлений пользователю.

Поддерживается:

- Telegram onboarding;
- Telegram delivery adapter;
- notification consumer;
- история уведомлений;
- фильтрация каналов уведомлений по типам alert-ов.

### Parser Health

Отвечает за диагностику состояния парсеров.

Parser-health помогает понять:

- доступен ли `go_fetcher`;
- работает ли WB parser;
- работает ли Ozon parser;
- есть ли cookies;
- не заблокировал ли маркетплейс запросы;
- на каком шаге произошла ошибка.

### Observability

В проекте есть observability-слой:

- Prometheus metrics;
- Grafana dashboards;
- Loki logs;
- Promtail Docker logs collection;
- PostgreSQL exporter;
- RabbitMQ metrics;
- notification consumer metrics;
- outbox worker metrics.

## Технологический стек

Backend:

- Python;
- Django;
- Django REST Framework;
- GraphQL;
- PostgreSQL;
- Redis;
- RabbitMQ;
- Docker;
- Docker Compose;
- Prometheus;
- Grafana;
- Loki;
- Promtail.

Fetcher:

- Go;
- HTTP API;
- marketplace parsers;
- Wildberries parser;
- Ozon parser;
- Playwright fallback for Ozon.

Infrastructure:

- Docker Compose;
- PostgreSQL exporter;
- RabbitMQ Management UI;
- Prometheus scraping;
- Grafana provisioning;
- Loki log storage.

## Структура проекта

```text
flashsale-backend/
├── backend/
│   ├── app/
│   ├── manage.py
│   ├── Dockerfile
│   └── .env.docker
├── go_fetcher/
│   ├── cmd/
│   ├── internal/
│   ├── secrets/
│   ├── Dockerfile
│   └── .env
├── grafana/
│   ├── dashboards/
│   ├── provisioning/
│   └── Dockerfile
├── prometheus/
│   └── prometheus.yml
├── loki/
│   └── loki-config.yml
├── promtail/
│   └── promtail-config.yml
├── docs/
│   ├── 01-local-run.md
│   ├── 02-cookies-refresh.md
│   ├── 03-parser-health.md
│   └── 04-demo-scenario.md
├── docker-compose.yml
└── README.md
```

## Документация

Подробные инструкции вынесены в отдельные файлы:

- `docs/01-local-run.md` — локальный запуск проекта;
- `docs/02-cookies-refresh.md` — обновление cookies для WB и Ozon;
- `docs/03-parser-health.md` — проверка состояния парсеров;
- `docs/04-demo-scenario.md` — demo-сценарий для показа проекта.

## Быстрый запуск

Подробная инструкция находится в файле:

[docs/01-local-run.md](docs/01-local-run.md)

Базовый запуск через Docker Compose:

```bash
docker compose up --build
```

После запуска нужно проверить:

```bash
docker compose ps
```

Основные сервисы должны быть в статусе `running` или `healthy`.

## Проверка parser-health

Подробная инструкция находится в файле:

[docs/03-parser-health.md](docs/03-parser-health.md)

Базовая проверка:

```bash
curl -X GET "http://127.0.0.1:8090/api/v1/parser/health"
```

Parser-health может вернуть один из статусов:

- `ok` — парсеры работают;
- `degraded` — часть проверок работает, часть нет;
- `error` — критическая ошибка проверки.

Важно: статус `degraded` не всегда означает ошибку backend. Маркетплейсы могут временно ограничивать запросы, возвращать antibot-страницы или требовать обновления cookies.

## Обновление cookies

Подробная инструкция находится в файле:

[docs/02-cookies-refresh.md](docs/02-cookies-refresh.md)

Cookies используются для того, чтобы fetcher мог обращаться к маркетплейсам с браузерным контекстом.

Ожидаемые файлы:

```text
go_fetcher/secrets/wb_cookie.txt
go_fetcher/secrets/ozon_cookie.txt
```

Если parser-health показывает ошибки вроде `blocked_by_antibot`, `rate_limited_or_blocked` или `cookie_present=false`, сначала нужно проверить cookies.

## Demo-сценарий

Подробная инструкция находится в файле:

[docs/04-demo-scenario.md](docs/04-demo-scenario.md)

Demo-сценарий показывает полный путь события:

```text
MonitoringTarget
-> Scanner Worker
-> Product Cache
-> go_fetcher
-> ProductSnapshot
-> Alert
-> OutboxEvent
-> RabbitMQ
-> Notification Consumer
-> Telegram Notification
-> Notification History API
```

## Текущий статус

Проект находится в стадии MVP.

Реализовано:

- backend API;
- интеграция с `go_fetcher`;
- мониторинг товаров;
- scanner worker;
- product cache layer;
- snapshots;
- alerts;
- outbox worker;
- GraphQL API layer;
- RabbitMQ integration;
- notification consumer;
- Telegram onboarding;
- Telegram notifications;
- notification history API;
- parser-health endpoint;
- Prometheus metrics;
- Grafana dashboards;
- Loki logs;
- Docker Compose infrastructure.

Возможные ограничения:

- WB и Ozon могут временно блокировать запросы;
- cookies периодически нужно обновлять;
- parser-health может показывать `degraded`, если маркетплейс ограничил доступ;
- для стабильной работы парсеров требуется актуальная конфигурация cookies и fallback-механизмов.
