# Flashsale Load Lab

The Load Lab answers three different questions without mixing their results:

1. **Capacity**: how many users and monitoring targets the Flashsale architecture can process when external systems are predictable.
2. **Integration**: whether real Wildberries, Ozon, browser fallback and Telegram integrations still work correctly.
3. **Chaos**: whether queues, retries, alerts and recovery work when dependencies become slow or unavailable.

All modes use isolated PostgreSQL, Prometheus, Loki and Grafana volumes. The normal project data is not modified.

The normal stack and a Load Lab stack cannot run at the same time because they intentionally reuse the same local ports and container names. Stop the normal stack before starting a lab.

## Safety properties

- Header authentication is enabled only when `LOAD_TESTING_ENABLED=true`.
- Only users named `loadtest_*` can be authenticated by load headers.
- Django refuses this mode when `APP_ENV=prod` or `APP_ENV=production`.
- Capacity and Chaos never call real marketplaces or Telegram.
- Grafana alerts from Capacity/Chaos are sent to the local simulator, not to the real Telegram contact point.
- Real integration mode uses a separate database, but it can call Ozon, Wildberries and Telegram. Keep its load low.
- Grafana alerts in both lab modes are routed to a local alert sink, never to the production Telegram contact point.

## Components

```text
k6
  -> real Django REST API
  -> fake Telegram getUpdates -> real Telegram bot handlers
  -> PostgreSQL / Redis
  -> Monitoring Scanner
  -> fake or real Fetcher
  -> snapshots / alerts / outbox
  -> RabbitMQ
  -> Notification Consumer
  -> fake or real Telegram

Prometheus <- all services + k6 remote write
Grafana    <- Prometheus + Loki
```

## Requirements

- Docker Desktop with Compose v2
- PowerShell 7 or Windows PowerShell 5.1
- At least 8 CPU threads and 12 GB free RAM for a local 1000-VU run
- For trustworthy 1000+ VU numbers, run k6 from a second machine or VPS. Running the generator and application on the same laptop measures the shared laptop limit.

If PowerShell blocks scripts for the current terminal:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

Create a local Load Lab settings file once:

```powershell
Copy-Item .\load_testing\.env.load.example .\load_testing\.env.load
```

Replace the two example keys in `.env.load` with long random local values. All Load Lab scripts automatically pass this file to Docker Compose. The file is ignored by Git.

Validate the package before the first run:

```powershell
.\load_testing\scripts\Test-LoadLabConfiguration.ps1
```

---

# Capacity mode

## 1. Start an isolated lab and seed 1000 users / 5000 targets

```powershell
.\load_testing\scripts\Start-CapacityLab.ps1 `
  -Users 1000 `
  -TargetsPerUser 5 `
  -ResetData
```

This creates 1000 real Django users and 5000 monitoring targets in the isolated Load Lab database. API traffic, scanner traffic and Telegram-bot ingress can then be tested independently or together.

This creates a hot/warm/cold product distribution:

- 50% of targets share 100 popular products;
- 30% share 500 medium products;
- 20% are unique.

This is intentional: it measures Redis cache hits, shared refresh locks and cache-stampede protection.

## 2. Run a smoke test first

```powershell
.\load_testing\scripts\Run-Smoke.ps1
```

## 3. Run the launch-day profile

```powershell
.\load_testing\scripts\Run-Capacity.ps1 `
  -PeakVUs 1000 `
  -RampUp 5m `
  -Hold 15m `
  -RampDown 3m
```

Default SLOs:

- HTTP failure rate below 1%;
- HTTP P95 below 750 ms;
- HTTP P99 below 2000 ms;
- checks above 99%;
- no dropped iterations.

The script exits with a non-zero code when a k6 threshold fails.

## 4. Find the breaking point

```powershell
.\load_testing\scripts\Run-Breakpoint.ps1 `
  -StartRate 10 `
  -MaxRate 500 `
  -MaxVUs 3000
```

This increases the arrival rate independently of server latency. It reveals the rate where the system starts queueing, dropping iterations or violating latency SLOs.

## 5. Load the Telegram bot ingress

The Capacity lab also starts the real Telegram polling process against fake Telegram.
Inject synthetic private-chat commands at a controlled rate:

```powershell
.\load_testing\scripts\Run-TelegramBotLoad.ps1 `
  -UpdatesPerSecond 20 `
  -Duration 10m
```

This tests `getUpdates`, routing, user-context lookup, `/products`, `/notifications`, `/help`, reply rate limits and outgoing replies without contacting Telegram. The Load Lab dashboard shows queued/delivered updates, processing errors and repeated replies.

## 6. Create a notification storm

```powershell
.\load_testing\scripts\Trigger-NotificationStorm.ps1 -Count 1000
```

This creates real `Alert` and `OutboxEvent` rows. The normal outbox worker, RabbitMQ and notification consumer must drain them into fake Telegram without data loss or duplicates.

## 7. Check health during a run

```powershell
.\load_testing\scripts\Show-LabHealth.ps1
```

Open:

- Grafana: <http://127.0.0.1:3000>
- Dashboard: **Flashsale Load Lab**
- Prometheus: <http://127.0.0.1:9090>
- k6 live dashboard while a test runs: <http://127.0.0.1:5665>

## 8. Generate a Markdown report

```powershell
.\load_testing\scripts\Generate-Report.ps1 `
  -Summary .\load_testing\results\capacity-summary.json `
  -Output .\load_testing\results\capacity-report.md `
  -Window 1h
```

HTML and JSON artifacts are written to `load_testing/results/`.

## 9. Stop the lab

Keep data:

```powershell
.\load_testing\scripts\Stop-CapacityLab.ps1
```

Delete only Load Lab data:

```powershell
.\load_testing\scripts\Stop-CapacityLab.ps1 -DeleteData
```

---

# Integration mode

Integration mode uses the real fetcher, Ozon browser fallback and Telegram configuration from the project. It must remain low-volume.

## Automatic collection of 50 real product links

No manual search is required. `/app/loadcatalog`:

1. runs existing WB and Ozon search parsers for several categories;
2. deduplicates candidates;
3. validates each candidate with the real product parser;
4. saves only successful products to `load_testing/data/integration-products.json`.

Start and collect:

```powershell
.\load_testing\scripts\Start-IntegrationLab.ps1 `
  -Users 25 `
  -TargetsPerUser 2 `
  -ResetData
```

To test real outbound Telegram delivery, provide one dedicated test chat ID:

```powershell
.\load_testing\scripts\Start-IntegrationLab.ps1 `
  -Users 10 `
  -TargetsPerUser 2 `
  -TelegramChatId "YOUR_TEST_CHAT_ID" `
  -ResetData
```

Every integration user uses that dedicated chat. Do not use a production customer chat. Grafana alerts remain local; only application notifications are sent to this chat.

Send one controlled notification after startup:

```powershell
.\load_testing\scripts\Trigger-IntegrationNotification.ps1 -Count 1
```

Incoming Telegram polling is disabled in Integration mode by default to avoid consuming updates from a real bot that may be used elsewhere. Start it only with a dedicated test bot:

```powershell
.\load_testing\scripts\Start-IntegrationLab.ps1 `
  -Users 10 `
  -TargetsPerUser 2 `
  -TelegramChatId "YOUR_TEST_CHAT_ID" `
  -StartTelegramBot `
  -ResetData
```

Run the test:

```powershell
.\load_testing\scripts\Run-Integration.ps1 `
  -VUs 20 `
  -Duration 10m
```

Stop Integration Lab while keeping its isolated data:

```powershell
.\load_testing\scripts\Stop-IntegrationLab.ps1
```

Delete only Integration Lab volumes:

```powershell
.\load_testing\scripts\Stop-IntegrationLab.ps1 -DeleteData
```

Expected integration failures such as marketplace 403/429 are measured separately from internal 5xx errors. A high external failure rate is not automatically proof that the backend cannot handle load.

---

# Chaos mode

## External dependency chaos

```powershell
.\load_testing\scripts\Run-Chaos.ps1 -VUs 300 -Duration 16m
```

The controller changes the simulator while traffic continues:

1. normal;
2. slow responses;
3. partial errors and rate limits;
4. complete outage;
5. recovery;
6. 15% price drop;
7. Telegram 429;
8. recovery.

Measure whether stale cache, outbox, retries, DLQ, alerts and recovery behave correctly.

## Infrastructure chaos

Run this in a second terminal while Capacity or Chaos traffic is active:

```powershell
.\load_testing\scripts\Invoke-InfrastructureChaos.ps1 `
  -ConfirmDestructiveChaos `
  -FailureSeconds 30
```

It interrupts only the isolated Load Lab containers:

- Redis outage;
- notification consumer outage;
- RabbitMQ restart;
- PostgreSQL pause.

It does not delete data. Verify that alerts fire and resolve, queues drain, messages are not lost and duplicate deliveries do not appear.

---

# Main bottleneck calculation

For monitoring, user count alone is not enough. The scanner throughput requirement is:

```text
required targets/sec = active targets / check interval seconds
```

For 5000 targets checked every 15 minutes:

```text
5000 / 900 = 5.56 targets/sec
```

For 5000 targets checked every 5 minutes:

```text
5000 / 300 = 16.67 targets/sec
```

Compare this with `rate(monitoring_target_processing_total[5m])`. If actual sustained throughput is below the requirement, overdue targets will grow even when the API itself remains fast.

# Result interpretation

A useful final statement looks like this:

```text
On hardware X with 4 backend workers and 1 scanner process:
- stable at 1000 registered users / 5000 targets;
- stable at 120 concurrent API users and 85 req/s;
- P95 = 420 ms, P99 = 980 ms;
- scanner = 18 targets/s;
- no outbox failures or DLQ messages;
- breakpoint begins at 170 req/s because PostgreSQL connections and API latency rise;
- after RabbitMQ restart, the queue drains in 42 seconds without duplicates.
```

Do not describe “1000 clients” only as 1000 VUs. Record registered users, active VUs, request rate, target count, scanner throughput and notification rate separately.
