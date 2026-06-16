import atexit
import os
from pathlib import Path

from flask import Flask

from ozon_browser_fetcher.app.api.views import bp
from ozon_browser_fetcher.app.browser.worker import (
    init_browser_worker,
    shutdown_browser_worker,
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
