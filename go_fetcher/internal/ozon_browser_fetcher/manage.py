import atexit
import os
import time
from pathlib import Path

from flask import Flask, g, request

from ozon_browser_fetcher.app.api.views import bp
from ozon_browser_fetcher.app.browser.worker import (
    init_browser_worker,
    shutdown_browser_worker,
)
from ozon_browser_fetcher.app.metrics import (
    OZON_BROWSER_HTTP_REQUEST_DURATION_SECONDS,
    OZON_BROWSER_HTTP_REQUESTS_IN_PROGRESS,
    OZON_BROWSER_HTTP_REQUESTS_TOTAL,
    normalize_route,
    status_class,
)


def resolve_cookie_path() -> str:
    env_path = os.getenv("OZON_COOKIE_PATH")

    if env_path:
        return str(Path(env_path).expanduser().resolve())

    docker_path = Path("/app/secrets/ozon_cookie.txt")

    if docker_path.exists():
        return str(docker_path)

    current_file = Path(__file__).resolve()

    go_fetcher_root = current_file.parents[2]
    local_path = go_fetcher_root / "secrets" / "ozon_cookie.txt"

    return str(local_path)


app = Flask(__name__)
app.register_blueprint(bp)


@app.before_request
def start_request_metrics() -> None:
    route = normalize_route(request.path)
    method = request.method.upper()

    g.metrics_route = route
    g.metrics_method = method
    g.metrics_started_at = time.monotonic()

    OZON_BROWSER_HTTP_REQUESTS_IN_PROGRESS.labels(
        route=route,
        method=method,
    ).inc()


@app.after_request
def finish_request_metrics(response):
    route = getattr(
        g,
        "metrics_route",
        normalize_route(request.path),
    )
    method = getattr(
        g,
        "metrics_method",
        request.method.upper(),
    )
    started_at = getattr(
        g,
        "metrics_started_at",
        time.monotonic(),
    )

    OZON_BROWSER_HTTP_REQUESTS_TOTAL.labels(
        route=route,
        method=method,
        status_class=status_class(response.status_code),
    ).inc()

    OZON_BROWSER_HTTP_REQUEST_DURATION_SECONDS.labels(
        route=route,
        method=method,
    ).observe(
        time.monotonic() - started_at
    )

    OZON_BROWSER_HTTP_REQUESTS_IN_PROGRESS.labels(
        route=route,
        method=method,
    ).dec()

    return response


def startup() -> None:
    cookie_path = resolve_cookie_path()

    print(f"Ozon cookie path: {cookie_path}")

    init_browser_worker(cookie_path=cookie_path)


startup()
atexit.register(shutdown_browser_worker)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8095,
        threaded=True,
        debug=False,
    )
