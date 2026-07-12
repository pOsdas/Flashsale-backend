# Flashsale Load Lab - инструкция на русском

> Полный пошаговый сценарий запуска, диагностики и результатов находится в `load_testing/RUNBOOK_RU.md`.

Load Lab запускается отдельно от обычного проекта. Обычный стек нужно остановить, потому что лаборатория использует те же локальные порты и container names, но отдельные Docker volumes.

## Подготовка

```powershell
docker compose down --remove-orphans
Copy-Item .\load_testing\.env.load.example .\load_testing\.env.load
notepad .\load_testing\.env.load
```

Замени две строки `replace-with-...` на длинные случайные локальные ключи.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\load_testing\scripts\Test-LoadLabConfiguration.ps1
```

## Capacity: предел собственной архитектуры

Создать 1000 пользователей и 5000 targets в отдельной базе:

```powershell
.\load_testing\scripts\Start-CapacityLab.ps1 `
  -Users 1000 `
  -TargetsPerUser 5 `
  -ResetData
```

Сначала smoke:

```powershell
.\load_testing\scripts\Run-Smoke.ps1
```

Основной запуск на 1000 одновременных VU:

```powershell
.\load_testing\scripts\Run-Capacity.ps1 `
  -PeakVUs 1000 `
  -RampUp 5m `
  -Hold 15m `
  -RampDown 3m
```

Поиск точки отказа:

```powershell
.\load_testing\scripts\Run-Breakpoint.ps1 `
  -StartRate 10 `
  -MaxRate 500 `
  -MaxVUs 3000
```

Нагрузка на реальные handlers Telegram-бота через fake Telegram:

```powershell
.\load_testing\scripts\Run-TelegramBotLoad.ps1 `
  -UpdatesPerSecond 20 `
  -Duration 10m
```

Шторм из 1000 настоящих Alert + OutboxEvent:

```powershell
.\load_testing\scripts\Trigger-NotificationStorm.ps1 -Count 1000
```

Состояние системы:

```powershell
.\load_testing\scripts\Show-LabHealth.ps1
```

Открыть:

- Grafana: http://127.0.0.1:3000
- Prometheus: http://127.0.0.1:9090
- k6 live dashboard во время теста: http://127.0.0.1:5665

Отчёт:

```powershell
.\load_testing\scripts\Generate-Report.ps1 `
  -Summary .\load_testing\results\capacity-summary.json `
  -Output .\load_testing\results\capacity-report.md `
  -Window 1h
```

Остановить:

```powershell
.\load_testing\scripts\Stop-CapacityLab.ps1
```

Остановить и удалить только данные Capacity Lab:

```powershell
.\load_testing\scripts\Stop-CapacityLab.ps1 -DeleteData
```

## Integration: настоящие WB, Ozon и Telegram

Скрипт автоматически пытается получить и проверить 25 WB + 25 Ozon ссылок через существующие search/product parsers. Ручной поиск не нужен. Фактическое число может быть меньше, если маркетплейс временно блокирует часть запросов.

```powershell
.\load_testing\scripts\Start-IntegrationLab.ps1 `
  -Users 25 `
  -TargetsPerUser 2 `
  -ResetData
```

Запустить небольшую реальную нагрузку:

```powershell
.\load_testing\scripts\Run-Integration.ps1 `
  -VUs 20 `
  -Duration 10m
```

Для одной контролируемой проверки реального Telegram используй отдельный тестовый chat ID:

```powershell
.\load_testing\scripts\Start-IntegrationLab.ps1 `
  -Users 10 `
  -TargetsPerUser 2 `
  -TelegramChatId "TEST_CHAT_ID" `
  -ResetData

.\load_testing\scripts\Trigger-IntegrationNotification.ps1 -Count 1
```

Входящий polling реального Telegram-бота по умолчанию не запускается. Флаг `-StartTelegramBot` используй только с отдельным тестовым ботом.

```powershell
.\load_testing\scripts\Stop-IntegrationLab.ps1 -DeleteData
```

## Chaos: контролируемые отказы

Ошибки fake Fetcher/Telegram, timeout, 429, 5xx, outage, price shock и восстановление:

```powershell
.\load_testing\scripts\Run-Chaos.ps1 -VUs 300 -Duration 16m
```

Перезапуски/паузы Redis, consumer, RabbitMQ и PostgreSQL только внутри Capacity Lab:

```powershell
.\load_testing\scripts\Invoke-InfrastructureChaos.ps1 `
  -ConfirmDestructiveChaos `
  -FailureSeconds 30
```

## Как читать результат

Не ограничивай итог фразой «1000 пользователей выдержал». Запиши:

- число зарегистрированных пользователей и targets;
- максимальные VU и request rate;
- HTTP P95/P99 и error rate;
- scanner throughput и количество overdue targets;
- максимум pending/failed outbox;
- максимум RabbitMQ backlog и DLQ;
- скорость notification consumer;
- CPU/RAM и подключения PostgreSQL;
- время восстановления после chaos;
- наличие потерь или дублей уведомлений.

Надёжный тест 1000+ VU лучше запускать с отдельной машины-генератора, иначе измеряется общий предел одного компьютера, на котором одновременно работают приложение и k6.
