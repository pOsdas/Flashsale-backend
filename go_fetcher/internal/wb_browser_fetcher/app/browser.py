import threading
from pathlib import Path
from typing import Dict, List

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright


def parse_cookie_header(cookie_header: str) -> List[Dict]:
    cookies: List[Dict] = []

    for part in cookie_header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue

        name, value = part.split("=", 1)
        name = name.strip()
        if not name:
            continue

        cookies.append(
            {
                "name": name,
                "value": value.strip(),
                "domain": ".wildberries.ru",
                "path": "/",
                "secure": True,
            }
        )

    return cookies


class WBBrowser:
    def __init__(self, cookie_path: str) -> None:
        self.cookie_path = Path(cookie_path)
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.cookie_mtime_ns = -1
        self.lock = threading.Lock()

    def start(self) -> None:
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
        )
        self._reload_cookies(force=True)
        self.page = self.context.new_page()
        self.page.set_default_timeout(30_000)
        self.page.set_default_navigation_timeout(30_000)
        self.page.goto(
            "https://www.wildberries.ru/",
            wait_until="domcontentloaded",
        )

    def _reload_cookies(self, force: bool = False) -> None:
        if self.context is None:
            raise RuntimeError("browser context is not started")

        stat = self.cookie_path.stat()
        if not force and stat.st_mtime_ns == self.cookie_mtime_ns:
            return

        cookie_header = self.cookie_path.read_text(encoding="utf-8").strip()
        cookies = parse_cookie_header(cookie_header)
        if not cookies:
            raise RuntimeError("WB cookie file is empty or invalid")

        self.context.clear_cookies()
        self.context.add_cookies(cookies)
        self.cookie_mtime_ns = stat.st_mtime_ns

    def fetch(self, url: str) -> Dict:
        with self.lock:
            if self.page is None or self.context is None:
                raise RuntimeError("WB browser is not ready")

            self._reload_cookies()
            result = self.page.evaluate(
                """
                async (url) => {
                    const response = await fetch(url, {
                        method: "GET",
                        credentials: "include",
                        headers: {"Accept": "application/json, text/plain, */*"}
                    });
                    return {
                        status_code: response.status,
                        body: await response.text()
                    };
                }
                """,
                url,
            )

            return result

    def is_ready(self) -> bool:
        return bool(self.browser and self.browser.is_connected() and self.page)

    def stop(self) -> None:
        if self.context is not None:
            self.context.close()
        if self.browser is not None:
            self.browser.close()
        if self.playwright is not None:
            self.playwright.stop()

