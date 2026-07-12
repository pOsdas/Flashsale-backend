# Flashsale Load Lab - полный порядок запуска

## Почему первый запуск завершился ошибкой

Старый `Common.ps1` проверял volume командой `docker volume inspect`. Отсутствующий volume - нормальная ситуация при первом запуске, но PowerShell с `ErrorActionPreference=Stop` воспринимал stderr Docker как исключение. Скрипт останавливался до `docker compose up`, поэтому контейнеры и volumes не создавались.

В исправленной версии отсутствующий volume просто пропускается. Создавать volumes вручную не требуется: Docker Compose создаст их при запуске стенда.

## 0. Подготовка один раз

Из корня репозитория:

```powershell
docker compose down --remove-orphans

Copy-Item `
  .\load_testing\.env.load.example `
  .\load_testing\.env.load `
  -ErrorAction SilentlyContinue

notepad .\load_testing\.env.load
```

В `.env.load` замени две строки `replace-with-...` на длинные случайные локальные значения.

Разрешить скрипты только для текущего окна PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

Проверить конфигурацию:

```powershell
.\load_testing\scripts\Test-LoadLabConfiguration.ps1
```

## 1. Capacity Lab

### 1.1 Чистый запуск

```powershell
.\load_testing\scripts\Start-CapacityLab.ps1 `
  -Users 1000 `
  -TargetsPerUser 5 `
  -ResetData
```

Скрипт сам:

1. остановит старый stack проекта;
2. удалит только load volumes, если они существуют;
3. создаст новые volumes;
4. поднимет PostgreSQL, Redis, RabbitMQ и fake external simulator;
5. применит миграции;
6. поднимет backend;
7. создаст 1000 пользователей и 5000 targets;
8. поднимет scanner, outbox worker, notification consumer и Telegram bot;
9. поднимет Prometheus и Grafana.

После успешного запуска:

- Grafana: http://127.0.0.1:3000 (`admin` / `admin`)
- Prometheus: http://127.0.0.1:9090
- Simulator state: http://127.0.0.1:8099/__control/state
- k6 live dashboard: http://127.0.0.1:5665 - доступен только во время выполняющегося k6-теста

Проверить здоровье:

```powershell
.\load_testing\scripts\Show-LabHealth.ps1 -Mode capacity
```

### 1.2 Smoke test

Всегда запускать первым:

```powershell
.\load_testing\scripts\Run-Smoke.ps1
```

Результаты:

- `load_testing/results/smoke-summary.json`
- `load_testing/results/smoke-report.html`
- консоль k6
- Grafana dashboard `Flashsale Load Lab`

Если k6 завершился ненулевым кодом из-за threshold, summary и HTML обычно всё равно создаются. Это означает FAIL теста, а не поломку PowerShell-скрипта.

### 1.3 Основной Capacity test на 1000 VU

```powershell
.\load_testing\scripts\Run-Capacity.ps1 `
  -PeakVUs 1000 `
  -RampUp 5m `
  -Hold 15m `
  -RampDown 3m
```

Результаты:

- `load_testing/results/capacity-summary.json`
- `load_testing/results/capacity-report.html`
- k6 live dashboard во время теста
- Prometheus history
- Grafana `Flashsale Load Lab`

Сформировать итоговый Markdown:

```powershell
.\load_testing\scripts\Generate-Report.ps1 `
  -Summary .\load_testing\results\capacity-summary.json `
  -Output .\load_testing\results\capacity-report.md `
  -Window 1h
```

### 1.4 Breakpoint test

Запускать отдельно, когда другие k6-тесты не работают:

```powershell
.\load_testing\scripts\Run-Breakpoint.ps1 `
  -StartRate 10 `
  -MaxRate 500 `
  -MaxVUs 3000
```

Результаты:

- `load_testing/results/breakpoint-summary.json`
- `load_testing/results/breakpoint-report.html`
- Grafana и Prometheus

### 1.5 Telegram bot ingress

```powershell
.\load_testing\scripts\Run-TelegramBotLoad.ps1 `
  -UpdatesPerSecond 20 `
  -Duration 10m `
  -MaxVUs 500
```

Результаты:

- `load_testing/results/telegram-bot-summary.json`
- `load_testing/results/telegram-bot-report.html`
- fake Telegram counters в simulator state/metrics
- Telegram panels в Grafana

### 1.6 Notification storm

Можно запускать отдельно или во втором PowerShell-окне во время Capacity test:

```powershell
.\load_testing\scripts\Trigger-NotificationStorm.ps1 -Count 1000
```

Смотреть:

- Outbox dashboard
- RabbitMQ dashboard
- Notification Consumer dashboard
- `Flashsale Load Lab`
- simulator state

### 1.7 External Chaos

`Run-Chaos.ps1` сам создаёт трафик и переключает fake external services между latency, timeout, 429, 500 и outage:

```powershell
.\load_testing\scripts\Run-Chaos.ps1 `
  -VUs 300 `
  -Duration 16m
```

Результаты:

- `load_testing/results/chaos-summary.json`
- `load_testing/results/chaos-report.html`
- Grafana alerts отправляются в local simulator webhook, а не в рабочий Telegram

### 1.8 Infrastructure Chaos

Этот скрипт создаёт отказы, но сам не создаёт пользовательский трафик. Поэтому нужны два окна PowerShell.

Окно 1 - постоянная нагрузка:

```powershell
.\load_testing\scripts\Run-Capacity.ps1 `
  -PeakVUs 300 `
  -RampUp 1m `
  -Hold 12m `
  -RampDown 1m
```

Окно 2 - отказы:

```powershell
.\load_testing\scripts\Invoke-InfrastructureChaos.ps1 `
  -ConfirmDestructiveChaos `
  -FailureSeconds 30
```

Последовательно будут затронуты Redis, notification consumer, RabbitMQ и PostgreSQL. Смотреть восстановление, очереди, потери и дубли в Grafana.

### 1.9 Логи и диагностика

Все контейнеры:

```powershell
docker compose `
  --project-name flashsale-backend `
  --env-file .\load_testing\.env.load `
  -f .\docker-compose.yml `
  -f .\docker-compose.load.yml `
  ps
```

Свежие ошибки:

```powershell
docker compose `
  --project-name flashsale-backend `
  --env-file .\load_testing\.env.load `
  -f .\docker-compose.yml `
  -f .\docker-compose.load.yml `
  logs --since=10m --timestamps | `
  Select-String -Pattern "error|fatal|panic|traceback|exception|failed" -CaseSensitive:$false
```

Конкретный сервис:

```powershell
docker compose `
  --project-name flashsale-backend `
  --env-file .\load_testing\.env.load `
  -f .\docker-compose.yml `
  -f .\docker-compose.load.yml `
  logs --tail=200 monitoring_scanner
```

### 1.10 Остановка Capacity Lab

Сохранить тестовую БД и историю:

```powershell
.\load_testing\scripts\Stop-CapacityLab.ps1
```

Удалить только данные лаборатории:

```powershell
.\load_testing\scripts\Stop-CapacityLab.ps1 -DeleteData
```

## 2. Integration Lab

Capacity Lab сначала остановить:

```powershell
.\load_testing\scripts\Stop-CapacityLab.ps1
```

Чистый запуск с автоматическим поиском реальных товаров:

```powershell
.\load_testing\scripts\Start-IntegrationLab.ps1 `
  -Users 25 `
  -TargetsPerUser 2 `
  -ResetData
```

Проверить здоровье:

```powershell
.\load_testing\scripts\Show-LabHealth.ps1 -Mode integration
```

Запустить реальную небольшую нагрузку:

```powershell
.\load_testing\scripts\Run-Integration.ps1 `
  -VUs 20 `
  -Duration 10m
```

Результаты:

- `load_testing/data/integration-products.json`
- `load_testing/results/integration-summary.json`
- `load_testing/results/integration-report.html`
- Grafana и Prometheus

Для одного реального Telegram-уведомления перезапусти Integration Lab с отдельным тестовым chat ID:

```powershell
.\load_testing\scripts\Stop-IntegrationLab.ps1 -DeleteData

.\load_testing\scripts\Start-IntegrationLab.ps1 `
  -Users 10 `
  -TargetsPerUser 2 `
  -TelegramChatId "TEST_CHAT_ID" `
  -ResetData

.\load_testing\scripts\Trigger-IntegrationNotification.ps1 -Count 1
```

Входящий Telegram bot polling запускать только с отдельным тестовым ботом:

```powershell
.\load_testing\scripts\Start-IntegrationLab.ps1 `
  -Users 10 `
  -TargetsPerUser 2 `
  -StartTelegramBot `
  -ResetData
```

Остановить:

```powershell
.\load_testing\scripts\Stop-IntegrationLab.ps1
```

Удалить данные Integration Lab:

```powershell
.\load_testing\scripts\Stop-IntegrationLab.ps1 -DeleteData
```

## 3. Где смотреть итог

1. **PowerShell/k6** - immediate PASS/FAIL thresholds и ошибки запуска.
2. **k6 live dashboard** - `http://127.0.0.1:5665`, только пока k6 выполняется.
3. **HTML-файлы** - `load_testing/results/*-report.html`, открываются после теста в браузере.
4. **JSON summary** - `load_testing/results/*-summary.json`, машиночитаемые значения k6.
5. **Markdown report** - `capacity-report.md`, объединяет k6 и Prometheus.
6. **Grafana** - `http://127.0.0.1:3000`, dashboard `Flashsale Load Lab` и системные dashboards.
7. **Prometheus** - `http://127.0.0.1:9090`, точные временные ряды и PromQL.
8. **Simulator** - `http://127.0.0.1:8099/__control/state`, fake Fetcher/Telegram counters и alert sink.
9. **Docker logs** - причина 5xx, timeout, restart, parser и queue errors.

## 4. Рекомендуемый полный порядок

```text
Test-LoadLabConfiguration
Start-CapacityLab -ResetData
Show-LabHealth
Run-Smoke
Run-Capacity 1000 VU
Generate-Report
Run-Breakpoint
Run-TelegramBotLoad
Trigger-NotificationStorm
Run-Chaos
Capacity 300 VU + InfrastructureChaos in parallel
Stop-CapacityLab -DeleteData
Start-IntegrationLab -ResetData
Show-LabHealth integration
Run-Integration
Optional real Telegram notification
Stop-IntegrationLab -DeleteData
```
