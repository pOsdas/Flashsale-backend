import os
import threading
import time
import json
from pathlib import Path
from typing import Dict, List
from urllib.parse import parse_qs, quote_plus, urlparse

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from wb_browser_fetcher.app.validation import analyze_response


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
            os.getenv("WB_BROWSER_CDP_URL", "").strip()
            or default_cdp_url
        )
        self.connect_timeout_ms = self._get_positive_int(
            "WB_BROWSER_CDP_CONNECT_TIMEOUT_MS",
            15_000,
        )
        self.start_timeout_seconds = self._get_positive_int(
            "WB_BROWSER_CDP_START_TIMEOUT_SECONDS",
            90,
        )
        self.retry_delay_seconds = max(
            0.1,
            float(
                os.getenv(
                    "WB_BROWSER_CDP_RETRY_DELAY_SECONDS",
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

    def start(self) -> None:
        if self.is_ready():
            return

        self._connect_with_retry()
        self._reload_cookies(force=True)
        self.page = self.context.new_page()
        self.page.set_default_timeout(30_000)
        self.page.set_default_navigation_timeout(45_000)

        response = self.page.goto(
            "https://www.wildberries.ru/",
            wait_until="domcontentloaded",
        )
        print(
            "WB browser connected over CDP: "
            f"cdp_url={self.cdp_url}, "
            f"version={self.browser.version if self.browser else 'unknown'!r}, "
            f"homepage_status={response.status if response else 0}, "
            f"url={self.page.url}, "
            f"cookies={self._cookie_names()}",
            flush=True,
        )

    def _connect_with_retry(self) -> None:
        if not self.cdp_url:
            raise RuntimeError("WB_BROWSER_CDP_URL is empty")

        self._disconnect()
        self.playwright = sync_playwright().start()
        deadline = time.monotonic() + self.start_timeout_seconds
        last_error: BaseException | None = None

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
            "Failed to connect to external WB Chrome over CDP: "
            f"url={self.cdp_url}, "
            f"timeout={self.start_timeout_seconds}s, "
            f"last_error={last_error}"
        )

    def _reconnect(self) -> None:
        print(
            "WB CDP connection is unavailable; reconnecting",
            flush=True,
        )

        try:
            self._connect_with_retry()
            self._reload_cookies(force=True)
            self.page = self.context.new_page()
            self.page.set_default_timeout(30_000)
            self.page.set_default_navigation_timeout(45_000)
        except Exception:
            self.page = None
            self._disconnect()
            raise

    def _reload_cookies(self, force: bool = False) -> None:
        if self.context is None:
            raise RuntimeError("browser context is not connected")

        import_enabled = (
            os.getenv(
                "WB_BROWSER_IMPORT_COOKIE_FILE",
                "true",
            ).strip().lower()
            in {"1", "true", "yes", "on"}
        )

        if not import_enabled:
            return

        if not self.cookie_path.exists():
            print(
                "WB cookie file does not exist; "
                "persistent Chrome profile will be used: "
                f"path={self.cookie_path}",
                flush=True,
            )
            return

        stat = self.cookie_path.stat()
        if not force and stat.st_mtime_ns == self.cookie_mtime_ns:
            return

        cookie_header = self.cookie_path.read_text(
            encoding="utf-8"
        ).strip()
        cookies = parse_cookie_header(cookie_header)

        if not cookies:
            print(
                "WB cookie file is empty; "
                "persistent Chrome profile will be used",
                flush=True,
            )
            self.cookie_mtime_ns = stat.st_mtime_ns
            return

        self.context.add_cookies(cookies)
        self.cookie_mtime_ns = stat.st_mtime_ns
        print(
            "WB cookies imported without clearing profile: "
            f"count={len(cookies)}, "
            f"names={sorted(cookie['name'] for cookie in cookies)}",
            flush=True,
        )

    def _cookie_names(self) -> List[str]:
        if self.context is None:
            return []
        return sorted(cookie["name"] for cookie in self.context.cookies())

    @staticmethod
    def _request_kind(requested_url: str) -> str:
        parsed = urlparse(requested_url)
        if "/card/" in parsed.path or "/u-card/" in parsed.path:
            return "detail"
        if "/search/" in parsed.path:
            return "search"
        return ""

    @staticmethod
    def _frontend_page_url(requested_url: str) -> str:
        parsed = urlparse(requested_url)
        query = parse_qs(parsed.query)
        nm_id = str((query.get("nm") or [""])[0]).strip()
        if ("/card/" in parsed.path or "/u-card/" in parsed.path) and nm_id.isdigit():
            return f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx"

        search_query = str((query.get("query") or [""])[0]).strip()
        if "/search/" in parsed.path and search_query:
            return (
                "https://www.wildberries.ru/catalog/0/search.aspx?search="
                f"{quote_plus(search_query)}"
            )

        raise RuntimeError(f"unsupported WB browser fallback URL: {requested_url}")

    @staticmethod
    def _is_search_response_url(response_url: str) -> bool:
        parsed = urlparse(response_url)
        path = parsed.path.lower()
        host = (parsed.hostname or "").lower()
        if path.endswith("/search.aspx"):
            return False
        return (
            "/__internal/search/" in path
            or (
                (host == "search.wb.ru" or host.endswith(".search.wb.ru"))
                and path.endswith("/search")
            )
            or ("/exactmatch/" in path and path.endswith("/search"))
        )

    @staticmethod
    def _is_detail_response_url(response_url: str) -> bool:
        path = urlparse(response_url).path.lower()
        return (
            path.endswith("/detail")
            and (
                "/__internal/card/cards/" in path
                or "/__internal/u-card/cards/" in path
                or "/cards/" in path
            )
        )

    @classmethod
    def _is_candidate_response(cls, kind: str, response_url: str) -> bool:
        if kind == "search":
            return cls._is_search_response_url(response_url)
        if kind == "detail":
            return cls._is_detail_response_url(response_url)
        return False

    @staticmethod
    def _matches_requested_resource(
        kind: str,
        requested_url: str,
        response_url: str,
    ) -> bool:
        requested_query = parse_qs(urlparse(requested_url).query)
        response_query = parse_qs(urlparse(response_url).query)
        if kind == "detail":
            requested_nm = str((requested_query.get("nm") or [""])[0]).strip()
            response_nm = str((response_query.get("nm") or [""])[0]).strip()
            return bool(
                requested_nm
                and requested_nm in response_nm.replace(",", ";").split(";")
            )
        if kind == "search":
            requested_search = str(
                (requested_query.get("query") or [""])[0]
            ).strip().casefold()
            response_search = str(
                (
                    response_query.get("query")
                    or response_query.get("search")
                    or [""]
                )[0]
            ).strip().casefold()
            return bool(requested_search and requested_search == response_search)
        return False

    @staticmethod
    def _is_json_content_type(content_type: str) -> bool:
        media_type = str(content_type or "").split(";", 1)[0].strip().lower()
        return media_type == "application/json" or media_type.endswith("+json")

    @staticmethod
    def _payload_has_products_or_cards(body: str) -> bool:
        try:
            payload = json.loads(body)
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        if not isinstance(payload, dict):
            return False
        for container in (payload, payload.get("data")):
            if not isinstance(container, dict):
                continue
            for key in ("products", "cards"):
                if isinstance(container.get(key), list) and container[key]:
                    return True
        return False

    def _read_intercepted_response(self, requested_url: str, response) -> Dict:
        content_type = str(response.headers.get("content-type", ""))
        body = ""
        body_error = ""
        try:
            body = response.text()
        except Exception as exc:
            body_error = str(exc)

        body_size = len(body.encode("utf-8"))
        print(
            "WB browser intercepted response: "
            f"intercepted_url={response.url}, "
            f"status={response.status}, "
            f"content_type={content_type!r}, "
            f"body_size={body_size}, "
            f"body_error={body_error!r}",
            flush=True,
        )

        result = {
            "status_code": int(response.status),
            "body": body,
            "final_url": str(response.url),
            "content_type": content_type,
        }
        if response.status != 200:
            result["interception_error"] = (
                f"intercepted response status is {response.status}, expected 200"
            )
        elif not self._is_json_content_type(content_type):
            result["interception_error"] = "intercepted response Content-Type is not JSON"
        elif body_error:
            result["interception_error"] = (
                f"cannot read intercepted response body: {body_error}"
            )
        elif not self._payload_has_products_or_cards(body):
            result["interception_error"] = (
                "intercepted JSON does not contain products/cards"
            )
        return self._decorate_result(requested_url, result)

    def _capture_frontend_json(self, requested_url: str) -> Dict:
        if self.context is None:
            raise RuntimeError("WB browser context is not ready")

        kind = self._request_kind(requested_url)
        frontend_url = self._frontend_page_url(requested_url)
        temporary_page = self.context.new_page()
        temporary_page.set_default_timeout(30_000)
        temporary_page.set_default_navigation_timeout(45_000)
        captured: List[Dict] = []
        seen_responses = set()

        def capture_response(response) -> None:
            if (
                not self._is_candidate_response(kind, response.url)
                or not self._matches_requested_resource(
                    kind,
                    requested_url,
                    response.url,
                )
            ):
                return
            response_key = id(response)
            if response_key in seen_responses:
                return
            seen_responses.add(response_key)
            try:
                captured.append(
                    self._read_intercepted_response(requested_url, response)
                )
            except Exception as exc:
                print(
                    "WB browser intercepted response processing failed: "
                    f"intercepted_url={response.url}, "
                    f"status={response.status}, "
                    f"content_type={response.headers.get('content-type', '')!r}, "
                    "body_size=0, "
                    f"error={exc}",
                    flush=True,
                )

        # Register both mechanisms before navigation. expect_response provides
        # an exact network wait; the listener records every matching endpoint.
        temporary_page.on("response", capture_response)
        try:
            response_info = None
            wait_error = ""
            navigation = None
            try:
                with temporary_page.expect_response(
                    lambda response: (
                        self._is_candidate_response(kind, response.url)
                        and self._matches_requested_resource(
                            kind,
                            requested_url,
                            response.url,
                        )
                        and response.status == 200
                        and self._is_json_content_type(
                            response.headers.get("content-type", "")
                        )
                    ),
                    timeout=45_000,
                ) as response_info:
                    navigation = temporary_page.goto(
                        frontend_url,
                        wait_until="domcontentloaded",
                    )
            except Exception as exc:
                wait_error = str(exc)

            if (
                not wait_error
                and response_info is not None
                and response_info.value is not None
            ):
                expected_response = response_info.value
                if id(expected_response) not in seen_responses:
                    capture_response(expected_response)

            document_title = temporary_page.title()
            navigation_status = navigation.status if navigation else 0
            print(
                "WB browser frontend page loaded: "
                f"url={temporary_page.url}, "
                f"status={navigation_status}, "
                f"title={document_title!r}, "
                f"candidates={len(captured)}",
                flush=True,
            )

            for result in captured:
                result["document_title"] = document_title
                if (
                    not result.get("interception_error")
                    and self._is_acceptable_result(result)
                ):
                    return result

            errors = [
                str(
                    result.get("interception_error")
                    or result.get("validation_error")
                    or "invalid candidate"
                )
                for result in captured
            ]
            if wait_error:
                errors.append(f"network response wait failed: {wait_error}")
            raise RuntimeError(
                "WB frontend page did not produce valid search/detail JSON: "
                + ("; ".join(errors) if errors else "no matching network response")
            )
        finally:
            try:
                temporary_page.remove_listener("response", capture_response)
            except Exception:
                pass
            try:
                temporary_page.close()
            finally:
                print(
                    "WB browser temporary page closed: "
                    f"frontend_url={frontend_url}",
                    flush=True,
                )

    def fetch(self, url: str) -> Dict:
        with self.lock:
            if not self.is_ready():
                self._reconnect()

            if self.page is None or self.context is None:
                raise RuntimeError("WB browser is not ready")

            self._reload_cookies()
            result = self._capture_frontend_json(url)
            self._log_result("frontend_network_interception", result)
            return result

    def _decorate_result(self, requested_url: str, result: Dict) -> Dict:
        decorated = dict(result or {})
        body = str(decorated.get("body") or "")
        analysis = analyze_response(
            body,
            str(decorated.get("content_type") or ""),
            requested_url,
        )
        document_title = str(decorated.get("document_title") or "")
        if not document_title:
            try:
                document_title = self.page.title() if self.page is not None else ""
            except Exception:
                document_title = ""
        decorated.update(
            {
                "requested_url": requested_url,
                "final_url": str(decorated.get("final_url") or requested_url),
                "response_size": len(body.encode("utf-8")),
                "document_title": document_title,
                "response_kind": analysis["response_kind"],
                "requested_nm_id": analysis["requested_nm_id"],
                "parsed_nm_id": analysis["parsed_nm_id"],
                "valid": bool(analysis["valid"]),
                "validation_error": str(analysis["error"] or ""),
            }
        )
        return decorated

    @staticmethod
    def _is_acceptable_result(result: Dict) -> bool:
        status_code = int(result.get("status_code") or 0)
        return 200 <= status_code < 300 and bool(result.get("valid"))

    @staticmethod
    def _log_result(strategy: str, result: Dict) -> None:
        print(
            "WB browser fallback response: "
            f"strategy={strategy}, "
            f"requested_url={result.get('requested_url', '')}, "
            f"final_url={result.get('final_url', '')}, "
            f"status={int(result.get('status_code') or 0)}, "
            f"content_type={result.get('content_type', '')!r}, "
            f"response_size={int(result.get('response_size') or 0)}, "
            f"document_title={result.get('document_title', '')!r}, "
            f"response_kind={result.get('response_kind', '')}, "
            f"requested_nm_id={result.get('requested_nm_id', '')}, "
            f"parsed_nm_id={result.get('parsed_nm_id', '')}, "
            f"valid={bool(result.get('valid'))}, "
            f"validation_error={result.get('validation_error', '')!r}",
            flush=True,
        )

    def is_ready(self) -> bool:
        try:
            return bool(
                self.browser
                and self.browser.is_connected()
                and self.context
                and self.page
                and not self.page.is_closed()
            )
        except Exception:
            return False

    def get_health_snapshot(self) -> Dict:
        browser_version = ""
        pages_count = 0

        try:
            if self.browser is not None:
                browser_version = self.browser.version
        except Exception:
            browser_version = ""

        try:
            if self.context is not None:
                pages_count = len(self.context.pages)
        except Exception:
            pages_count = 0

        ready = self.is_ready()

        return {
            "status": "ok" if ready else "error",
            "browser_ready": ready,
            "cdp_connected": ready,
            "cdp_url": self.cdp_url,
            "browser_version": browser_version,
            "pages_count": pages_count,
        }

    def stop(self) -> None:
        if self.page is not None:
            try:
                self.page.close()
            except Exception:
                pass
            finally:
                self.page = None

        self._disconnect()

    def _disconnect(self) -> None:
        # Chrome is owned by the container startup script. Do not close the
        # persistent context or Browser here, otherwise Playwright would stop
        # the external browser process.
        self.context = None
        self.browser = None

        if self.playwright is not None:
            try:
                self.playwright.stop()
            except Exception:
                pass
            finally:
                self.playwright = None
