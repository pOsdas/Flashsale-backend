import os
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)

from ozon_browser_fetcher.app.browser.cookie_loader import (
    extract_cookie_names,
    load_cookie_header,
    parse_cookie_header,
)
from ozon_browser_fetcher.app.metrics import (
    OZON_BROWSER_LAST_SUCCESSFUL_START_TIMESTAMP_SECONDS,
    OZON_BROWSER_LIFECYCLE_TOTAL,
    OZON_BROWSER_PAGES_ACTIVE,
    OZON_BROWSER_PAGE_EVENTS_TOTAL,
    OZON_BROWSER_START_DURATION_SECONDS,
    OZON_BROWSER_WORKER_READY,
)


class BrowserManager:
    def __init__(self) -> None:
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.cookie_path: Optional[str] = None
        cdp_host = os.getenv(
            "BROWSER_CDP_HOST",
            "127.0.0.1",
        ).strip() or "127.0.0.1"
        cdp_port = os.getenv(
            "BROWSER_CDP_PORT",
            "9222",
        ).strip() or "9222"
        default_cdp_url = f"http://{cdp_host}:{cdp_port}"
        self.cdp_url = (
            os.getenv("OZON_BROWSER_CDP_URL", "").strip()
            or default_cdp_url
        )
        self.connect_timeout_ms = self._get_positive_int(
            "OZON_BROWSER_CDP_CONNECT_TIMEOUT_MS",
            15_000,
        )
        self.start_timeout_seconds = self._get_positive_int(
            "OZON_BROWSER_CDP_START_TIMEOUT_SECONDS",
            90,
        )
        self.retry_delay_seconds = max(
            0.1,
            float(
                os.getenv(
                    "OZON_BROWSER_CDP_RETRY_DELAY_SECONDS",
                    "1",
                )
            ),
        )

    @staticmethod
    def _get_positive_int(name: str, default: int) -> int:
        raw_value = os.getenv(name)

        if raw_value is None:
            return default

        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return default

        return value if value > 0 else default

    def start(self, cookie_path: str) -> None:
        self.cookie_path = cookie_path

        if self.is_ready():
            return

        started_at = time.monotonic()

        try:
            self._connect_with_retry()
            self._import_cookie_file()

            OZON_BROWSER_WORKER_READY.set(1)
            OZON_BROWSER_LIFECYCLE_TOTAL.labels(
                event="start_success",
            ).inc()
            OZON_BROWSER_LAST_SUCCESSFUL_START_TIMESTAMP_SECONDS.set(
                time.time()
            )

            browser_version = (
                self.browser.version
                if self.browser is not None
                else "unknown"
            )
            pages_count = (
                len(self.context.pages)
                if self.context is not None
                else 0
            )

            print(
                "Ozon browser connected over CDP: "
                f"url={self.cdp_url}, "
                f"version={browser_version!r}, "
                f"existing_pages={pages_count}",
                flush=True,
            )

        except Exception:
            OZON_BROWSER_WORKER_READY.set(0)
            OZON_BROWSER_LIFECYCLE_TOTAL.labels(
                event="start_error",
            ).inc()
            self._disconnect()
            raise

        finally:
            OZON_BROWSER_START_DURATION_SECONDS.observe(
                time.monotonic() - started_at
            )

    def _connect_with_retry(self) -> None:
        if not self.cdp_url:
            raise RuntimeError(
                "OZON_BROWSER_CDP_URL is empty"
            )

        self._disconnect()
        self.playwright = sync_playwright().start()

        deadline = (
            time.monotonic()
            + self.start_timeout_seconds
        )
        last_error: Optional[BaseException] = None

        while time.monotonic() < deadline:
            try:
                browser = self.playwright.chromium.connect_over_cdp(
                    self.cdp_url,
                    timeout=self.connect_timeout_ms,
                )

                if not browser.contexts:
                    raise RuntimeError(
                        "CDP browser has no persistent context"
                    )

                self.browser = browser
                self.context = browser.contexts[0]
                return

            except Exception as exc:
                last_error = exc
                time.sleep(self.retry_delay_seconds)

        raise RuntimeError(
            "Failed to connect to external Ozon Chrome over CDP: "
            f"url={self.cdp_url}, "
            f"timeout={self.start_timeout_seconds}s, "
            f"last_error={last_error}"
        )

    def _import_cookie_file(self) -> None:
        if self.context is None:
            raise RuntimeError(
                "Browser context is not connected"
            )

        import_enabled = (
            os.getenv(
                "OZON_BROWSER_IMPORT_COOKIE_FILE",
                "true",
            ).strip().lower()
            in {"1", "true", "yes", "on"}
        )

        if not import_enabled:
            print(
                "Ozon cookie file import is disabled; "
                "persistent Chrome profile will be used",
                flush=True,
            )
            return

        if not self.cookie_path:
            return

        cookie_file = Path(self.cookie_path)

        if not cookie_file.exists():
            print(
                "Ozon cookie file does not exist; "
                "persistent Chrome profile will be used: "
                f"path={cookie_file}",
                flush=True,
            )
            return

        cookie_header = load_cookie_header(str(cookie_file))
        parsed_cookies = parse_cookie_header(cookie_header)
        excluded_names = {
            item.strip()
            for item in os.getenv(
                "OZON_BROWSER_COOKIE_IMPORT_EXCLUDE_NAMES",
                "abt_data,__Secure-ETC",
            ).split(",")
            if item.strip()
        }
        cookies = [
            cookie
            for cookie in parsed_cookies
            if cookie.get("name") not in excluded_names
        ]

        if cookies:
            self.context.add_cookies(cookies)

        print(
            "Ozon cookies imported without clearing profile: "
            f"count={len(cookies)}, "
            f"excluded={len(parsed_cookies) - len(cookies)}, "
            f"names={extract_cookie_names(cookies)}",
            flush=True,
        )

    def _reconnect(self) -> None:
        print(
            "Ozon CDP connection is unavailable; reconnecting",
            flush=True,
        )
        OZON_BROWSER_WORKER_READY.set(0)
        OZON_BROWSER_LIFECYCLE_TOTAL.labels(
            event="reconnect_attempt",
        ).inc()

        try:
            self._connect_with_retry()
            self._import_cookie_file()
            OZON_BROWSER_WORKER_READY.set(1)
            OZON_BROWSER_LIFECYCLE_TOTAL.labels(
                event="reconnect_success",
            ).inc()
        except Exception:
            OZON_BROWSER_WORKER_READY.set(0)
            OZON_BROWSER_LIFECYCLE_TOTAL.labels(
                event="reconnect_error",
            ).inc()
            self._disconnect()
            raise

    def is_ready(self) -> bool:
        try:
            return bool(
                self.context is not None
                and self.browser is not None
                and self.browser.is_connected()
            )
        except Exception:
            return False

    def get_connection_snapshot(self) -> dict:
        browser_version = ""
        contexts_count = 0
        pages_count = 0

        try:
            if self.browser is not None:
                browser_version = self.browser.version
                contexts_count = len(self.browser.contexts)
        except Exception:
            browser_version = ""
            contexts_count = 0

        try:
            if self.context is not None:
                pages_count = len(self.context.pages)
        except Exception:
            pages_count = 0

        return {
            "cdp_url": self.cdp_url,
            "cdp_connected": self.is_ready(),
            "browser_version": browser_version,
            "contexts_count": contexts_count,
            "pages_count": pages_count,
        }

    def new_page(self) -> Page:
        if not self.is_ready():
            self._reconnect()

        if self.context is None:
            raise RuntimeError(
                "Browser context is not connected"
            )

        OZON_BROWSER_PAGE_EVENTS_TOTAL.labels(
            event="create_attempt",
        ).inc()

        try:
            page = self.context.new_page()
            page.set_default_timeout(
                self._get_positive_int(
                    "OZON_BROWSER_ACTION_TIMEOUT_MS",
                    8_000,
                )
            )
            page.set_default_navigation_timeout(
                self._get_positive_int(
                    "OZON_BROWSER_NAVIGATION_TIMEOUT_MS",
                    45_000,
                )
            )

            OZON_BROWSER_PAGES_ACTIVE.inc()
            OZON_BROWSER_PAGE_EVENTS_TOTAL.labels(
                event="created",
            ).inc()

            return page

        except Exception:
            OZON_BROWSER_PAGE_EVENTS_TOTAL.labels(
                event="create_error",
            ).inc()
            raise

    @staticmethod
    def close_page(page: Page) -> None:
        try:
            page.close()
            OZON_BROWSER_PAGE_EVENTS_TOTAL.labels(
                event="closed",
            ).inc()
        except Exception:
            OZON_BROWSER_PAGE_EVENTS_TOTAL.labels(
                event="close_error",
            ).inc()
        finally:
            OZON_BROWSER_PAGES_ACTIVE.dec()

    def stop(self) -> None:
        was_started = any(
            item is not None
            for item in (
                self.context,
                self.browser,
                self.playwright,
            )
        )

        OZON_BROWSER_WORKER_READY.set(0)
        self._disconnect()

        if was_started:
            OZON_BROWSER_LIFECYCLE_TOTAL.labels(
                event="stop",
            ).inc()

    def _disconnect(self) -> None:
        # The Google Chrome process is owned by the container startup script.
        # Closing its persistent context or Browser object here would stop the
        # external browser. Stopping Playwright is enough to drop the CDP
        # connection; the script terminates Chrome during container shutdown.
        self.context = None
        self.browser = None

        if self.playwright is not None:
            try:
                self.playwright.stop()
            except Exception:
                pass
            finally:
                self.playwright = None
