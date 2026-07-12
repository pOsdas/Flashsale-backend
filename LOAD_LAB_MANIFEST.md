# Flashsale Load Lab — delivery manifest

## Included modes

- **Capacity:** 1000 synthetic users, 5000+ monitoring targets, fake marketplace fetcher, fake Telegram, k6 launch-day/breakpoint/bot-ingress scenarios, real PostgreSQL/Redis/scanner/outbox/RabbitMQ/consumer pipeline.
- **Integration:** automatic WB/Ozon product catalog collection and validation, low-volume real parsers/browser fallback, optional controlled real Telegram notification.
- **Chaos:** controlled external latency/429/5xx/timeouts/price shocks plus isolated Redis/RabbitMQ/PostgreSQL/consumer interruptions.

## Safety

- Dedicated PostgreSQL, Prometheus, Loki and Grafana volumes for each lab mode.
- Load header authentication exists only when `LOAD_TESTING_ENABLED=true` and accepts only `loadtest_*` users.
- Capacity/Chaos never call real marketplaces or Telegram.
- Grafana lab alerts go to a local webhook sink, not the real Telegram contact point.
- Integration incoming bot polling is opt-in and should use a dedicated test bot.
- Runtime `.env`, marketplace cookies, `.git`, databases and generated result files are not included in this delivery.

## Main files

- `docker-compose.load.yml`
- `docker-compose.integration.yml`
- `load_testing/README.md`
- `load_testing/k6/*.js`
- `load_testing/simulator/*`
- `load_testing/scripts/*.ps1`
- `backend/app/api/v1/load_testing/*`
- `go_fetcher/cmd/loadcatalog/main.go`
- `grafana/dashboards/load-testing.json`

## Validation completed in the build environment

- Python syntax compilation passed.
- Every k6 JavaScript file passed `node --check`.
- Simulator `go test`, `go vet`, build and live HTTP contract tests passed.
- Dashboard JSON and provisioning YAML parsing passed.
- Grafana rule audit passed: unique UIDs, UID length <= 40, no nested `model.model`.
- Fake fetcher, price control and Telegram update queue were exercised through real HTTP routes.
- Generated report correctly returns `INCOMPLETE` instead of a false PASS when Prometheus data is unavailable.
- Delivery-file secret scan passed.

## Validation that must run on the user's machine

- `docker compose config` for both overlays.
- Full Docker image build and service startup.
- Django test suite inside the backend image.
- `go_fetcher/cmd/loadcatalog` build with the project's Go 1.26.3 toolchain and downloaded modules.
- Real WB/Ozon catalog collection, because it depends on current marketplace responses and local cookie files.

Run `load_testing/scripts/Test-LoadLabConfiguration.ps1` before the first lab startup.
