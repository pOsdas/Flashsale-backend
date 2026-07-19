# Marketplace fetcher

The Go fetcher uses regular HTTP parsers first and can fall back to browser
fetchers for Ozon and Wildberries.

## Browser architecture

The browser fetchers no longer call `playwright.chromium.launch()`.

Each browser-fetcher container now starts these processes in order:

1. Xvfb provides a real graphical display.
2. Openbox provides a lightweight Linux window manager.
3. A separate Google Chrome Stable process starts with a persistent profile and
   a local CDP port.
4. The startup script waits for `http://127.0.0.1:9222/json/version`.
5. Gunicorn starts the browser-fetcher API.
6. Playwright connects through `connect_over_cdp()` and controls pages in the
   already running Chrome process.

The CDP port is bound to `127.0.0.1` inside each container and is not published.
The API remains available on ports `8095` and `8096`.

Persistent Chrome profiles must be mounted at `/data/browser-profile`. They
store cookies, Local Storage, IndexedDB, cache, service workers, and marketplace
antibot session state between container restarts.

Use exactly one Chrome process per profile volume. Do not mount the same profile
volume into multiple replicas at the same time, because Chrome profiles are not
safe for concurrent writers.

## Docker build context

Both browser Dockerfiles install the official Google Chrome Stable amd64 package and therefore target `linux/amd64`. They expect `go_fetcher/internal` as their build context:

```yaml
build:
  context: ./go_fetcher/internal
  dockerfile: ozon_browser_fetcher/Dockerfile
```

and:

```yaml
build:
  context: ./go_fetcher/internal
  dockerfile: wb_browser_fetcher/Dockerfile
```

A standalone example is included in:

```text
docker-compose.browser-fetchers.example.yml
```

Use at least `1gb` of shared memory for each Chrome container:

```yaml
shm_size: "1gb"
```

Do not publish port `9222`. Playwright and Chrome run in the same container and
communicate through localhost.

## Ozon browser challenge

A normal Chrome session can initially receive:

```text
307 -> 403 Antibot Challenge Page
```

This first `403` is treated as an intermediate browser challenge. The parser
keeps the page alive and waits for JavaScript to submit `/abt/result` and for a
normal Ozon document to load. A final title `Похоже, нет соединения` is treated
as explicit fingerprint rejection.

Relevant settings:

```shell
OZON_BROWSER_CDP_URL=  # optional override
OZON_BROWSER_CHALLENGE_TIMEOUT_MS=25000
OZON_BROWSER_NAVIGATION_TIMEOUT_MS=45000
OZON_BROWSER_ACTION_TIMEOUT_MS=8000
```

The Ozon browser no longer spoofs a Windows/Edge User-Agent and no longer blocks
fonts, images, or other challenge resources. Chrome reports its real Linux
fingerprint.

## Browser process settings

Common environment variables used by the startup script:

```shell
BROWSER_CDP_HOST=127.0.0.1
BROWSER_CDP_PORT=9222
BROWSER_PROFILE_DIR=/data/browser-profile
BROWSER_DISPLAY=:99
BROWSER_WINDOW_SIZE=1400,900
BROWSER_LANGUAGE=ru-RU
TZ=Europe/Moscow
BROWSER_START_TIMEOUT_SECONDS=90
BROWSER_RUNTIME_DIR=/tmp/browser-runtime
```

Optional settings:

```shell
BROWSER_PROXY_SERVER=
BROWSER_PROXY_BYPASS_LIST=
BROWSER_EXTRA_ARGS=
BROWSER_DISABLE_SANDBOX=false
BROWSER_DISABLE_DEV_SHM_USAGE=false
```

Keep the Chrome sandbox enabled where possible. Set
`BROWSER_DISABLE_SANDBOX=true` only when the container runtime cannot start
Chrome with its normal sandbox and the Chrome log explicitly reports a sandbox
failure.

Chrome logs are written inside the container to:

```text
/tmp/browser-runtime/chrome.log
/tmp/browser-runtime/xvfb.log
/tmp/browser-runtime/openbox.log
```

## Cookies

Cookie files are optional when a persistent Chrome profile already contains a
working session:

```text
secrets/wb_cookie.txt
secrets/ozon_cookie.txt
```

By default, existing cookie files are imported without clearing cookies already
stored in the persistent profile. Ozon challenge cookies `abt_data` and
`__Secure-ETC` are excluded from file import by default because they are tied to
the browser/IP session; Chrome should obtain fresh values in its own profile.

Disable file import with:

```shell
OZON_BROWSER_IMPORT_COOKIE_FILE=false
OZON_BROWSER_COOKIE_IMPORT_EXCLUDE_NAMES=abt_data,__Secure-ETC
WB_BROWSER_IMPORT_COOKIE_FILE=false
```

## Browser fetcher endpoints

Ozon:

```shell
OZON_BROWSER_FETCHER_ENABLED=true
OZON_BROWSER_FETCHER_URL=http://ozon_browser_fetcher:8095
OZON_HTTP_PARSER_TIMEOUT_SECONDS=12
OZON_BROWSER_FETCHER_TIMEOUT_SECONDS=75
```

Wildberries:

```shell
WB_BROWSER_FETCHER_ENABLED=true
WB_BROWSER_FETCHER_URL=http://wb_browser_fetcher:8096
WB_BROWSER_FETCHER_TIMEOUT_SECONDS=60
```

Health endpoints:

```text
GET http://ozon_browser_fetcher:8095/api/v1/health
GET http://wb_browser_fetcher:8096/api/v1/health
```

Health responses include the CDP connection state, browser version, and page
count.

## Go commands

### Update cookie scripts

```shell
poetry run python ..\go_fetcher\tools\playwright\update_marketplace_cookie.py --marketplace wb
```
```shell
poetry run python ..\go_fetcher\tools\playwright\update_marketplace_cookie.py --marketplace ozon
```

And then:
```shell
powershell.exe `
   -NoProfile `
   -ExecutionPolicy Bypass `
   -File .\update-server-cookies.ps1
```

### Wildberries search

```shell
go run ./cmd/fetcher wb search --limit=100 "iphone"
```

### Wildberries product

```shell
go run ./cmd/fetcher wb product "302421341"
```

### Ozon search

```shell
go run ./cmd/fetcher ozon search --limit=100 "iphone"
```

### Ozon category

```shell
go run ./cmd/fetcher ozon category --limit=100 \
  "https://www.ozon.ru/category/svitery-dzhempery-i-kardigany-muzhskie-7554/"
```

### Ozon product

```shell
go run ./cmd/fetcher ozon product \
  "/product/sirop-topping-bez-sahara-nizkokaloriynyy-mr-djemius-zero-solenaya-karamel-330g-1919933573/"
```
