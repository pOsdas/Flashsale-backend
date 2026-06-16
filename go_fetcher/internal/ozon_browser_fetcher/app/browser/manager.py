import os
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Playwright, Request, Route, sync_playwright

from ozon_browser_fetcher.app.browser.cookie_loader import (
    extract_cookie_names,
    load_cookie_header,
    parse_cookie_header,
)


class BrowserManager:
    def __init__(self) -> None:
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None

    def start(self, cookie_path: str) -> None:
        if self.context is not None:
            return

        headless = os.getenv("OZON_BROWSER_HEADLESS", "true").lower() == "true"

        self.playwright = sync_playwright().start()

        self.browser = self.playwright.chromium.launch(
            headless=headless,
        )

        self.context = self.browser.new_context(
            viewport={
                "width": 1400,
                "height": 900,
            },
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            service_workers="block",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0"
            ),
            extra_http_headers={
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )

        self.context.route("**/*", self._route_handler)

        cookie_header = load_cookie_header(cookie_path)
        cookies = parse_cookie_header(cookie_header)

        if cookies:
            self.context.add_cookies(cookies)

        print(f"Ozon browser started. Headless: {headless}")
        print(f"Ozon cookies loaded: {len(cookies)}")
        print(f"Ozon cookie names: {extract_cookie_names(cookies)}")

    @staticmethod
    def _route_handler(route: Route, request: Request) -> None:
        blocked_resource_types = {
            "image",
            "media",
            "font",
        }

        if request.resource_type in blocked_resource_types:
            route.abort()
            return

        route.continue_()

    def new_page(self):
        if self.context is None:
            raise RuntimeError("Browser context is not started")

        page = self.context.new_page()
        page.set_default_timeout(5_000)
        page.set_default_navigation_timeout(30_000)

        return page

    def stop(self) -> None:
        if self.context is not None:
            self.context.close()
            self.context = None

        if self.browser is not None:
            self.browser.close()
            self.browser = None

        if self.playwright is not None:
            self.playwright.stop()
            self.playwright = None
