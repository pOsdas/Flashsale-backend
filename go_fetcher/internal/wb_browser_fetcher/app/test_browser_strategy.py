import json
import threading
import unittest

from wb_browser_fetcher.app.browser import WBBrowser


DETAIL_URL = "https://www.wildberries.ru/__internal/u-card/cards/v4/detail?nm=881219291"
SEARCH_URL = (
    "https://www.wildberries.ru/__internal/search/exactmatch/ru/common/v18/search"
    "?query=iphone&resultset=catalog"
)


def search_endpoint(resultset="catalog"):
    return (
        "https://www.wildberries.ru/__internal/u-search/exactmatch/ru/common/v18/search"
        f"?query=iphone&resultset={resultset}"
    )


class FakeResponse:
    def __init__(self, url, body, content_type="application/json", status=200):
        self.url = url
        self.status = status
        self.headers = {"content-type": content_type}
        self._body = body
        self.text_calls = 0

    def text(self):
        self.text_calls += 1
        return self._body


class FakeExpectedResponse:
    def __init__(self, page, predicate):
        self.page = page
        self.predicate = predicate
        self.value = None

    def __enter__(self):
        self.page.expectation = self
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None and self.value is None:
            raise TimeoutError("no valid matching response")


class FakeNavigation:
    status = 200


class FakeTemporaryPage:
    def __init__(self, responses):
        self.responses = responses
        self.listeners = []
        self.expectation = None
        self.closed = False
        self.url = "about:blank"
        self.listener_was_registered_before_goto = False

    def set_default_timeout(self, timeout):
        self.default_timeout = timeout

    def set_default_navigation_timeout(self, timeout):
        self.navigation_timeout = timeout

    def on(self, event, callback):
        if event != "response":
            raise AssertionError(f"unexpected event: {event}")
        self.listeners.append(callback)

    def remove_listener(self, event, callback):
        if event != "response":
            raise AssertionError(f"unexpected event: {event}")
        if callback in self.listeners:
            self.listeners.remove(callback)

    def expect_response(self, predicate, timeout):
        self.expect_timeout = timeout
        return FakeExpectedResponse(self, predicate)

    def goto(self, url, wait_until):
        self.url = url
        self.listener_was_registered_before_goto = bool(self.listeners)
        for response in self.responses:
            for listener in list(self.listeners):
                listener(response)
            if self.expectation and self.expectation.predicate(response):
                self.expectation.value = response
                break
        return FakeNavigation()

    def title(self):
        return "Wildberries frontend page"

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, temporary_page):
        self.temporary_page = temporary_page

    def new_page(self):
        return self.temporary_page


class FakeMainPage:
    def title(self):
        return "Wildberries"


class StrategyBrowser(WBBrowser):
    def __init__(self, responses):
        self.lock = threading.Lock()
        self.page = FakeMainPage()
        self.temporary_page = FakeTemporaryPage(responses)
        self.context = FakeContext(self.temporary_page)
        self.default_request_timeout_ms = 60_000
        self.network_wait_safety_margin_ms = 5_000
        self.network_wait_min_ms = 1_000
        self.network_wait_max_ms = 40_000

    def is_ready(self):
        return True

    def _reload_cookies(self, force=False):
        return None


def product_body(product_id=881219291, container="products"):
    return json.dumps(
        {
            container: [
                {
                    "id": product_id,
                    "name": "iPhone 17 Pro 512 GB",
                    "salePriceU": 14999000,
                    "totalQuantity": 1,
                }
            ]
        }
    )


class WBBrowserStrategyTests(unittest.TestCase):
    def test_text_plain_catalog_json_is_accepted(self):
        response = FakeResponse(
            search_endpoint(),
            product_body(),
            "text/plain; charset=UTF-8",
        )
        browser = StrategyBrowser([response])

        result = browser.fetch(SEARCH_URL, request_timeout_ms=35_000)

        self.assertTrue(result["valid"])
        self.assertTrue(result["json_decode_success"])
        self.assertEqual(result["response_kind"], "search_catalog")
        self.assertEqual(result["resultset"], "catalog")
        self.assertEqual(result["products_count"], 1)
        self.assertEqual(result["content_type"], "text/plain; charset=UTF-8")
        self.assertEqual(browser.temporary_page.listeners, [])
        self.assertTrue(browser.temporary_page.closed)

    def test_html_body_is_rejected(self):
        browser = StrategyBrowser(
            [FakeResponse(search_endpoint(), "<html>Angie</html>", "text/html")]
        )

        with self.assertRaisesRegex(RuntimeError, "HTML"):
            browser.fetch(SEARCH_URL, 35_000)

    def test_text_plain_non_json_is_rejected(self):
        browser = StrategyBrowser(
            [FakeResponse(search_endpoint(), "not json", "text/plain")]
        )

        with self.assertRaisesRegex(RuntimeError, "not Wildberries JSON"):
            browser.fetch(SEARCH_URL, 35_000)

    def test_filters_resultset_is_not_accepted(self):
        browser = StrategyBrowser(
            [FakeResponse(search_endpoint("filters"), product_body(), "text/plain")]
        )

        with self.assertRaisesRegex(RuntimeError, "resultset=filters"):
            browser.fetch(SEARCH_URL, 35_000)

    def test_catalog_resultset_with_products_is_accepted(self):
        browser = StrategyBrowser(
            [FakeResponse(search_endpoint("catalog"), product_body(), "text/plain")]
        )

        result = browser.fetch(SEARCH_URL, 35_000)

        self.assertTrue(result["valid"])
        self.assertEqual(result["resultset"], "catalog")

    def test_first_invalid_second_valid_returns_second(self):
        invalid = FakeResponse(search_endpoint("filters"), product_body(), "text/plain")
        valid = FakeResponse(search_endpoint("catalog"), product_body(), "text/plain")
        browser = StrategyBrowser([invalid, valid])

        result = browser.fetch(SEARCH_URL, 35_000)

        self.assertEqual(result["final_url"], valid.url)
        self.assertEqual(invalid.text_calls, 1)
        self.assertEqual(valid.text_calls, 1)

    def test_wait_stops_after_first_valid_response(self):
        valid = FakeResponse(search_endpoint(), product_body(), "text/plain")
        later = FakeResponse(search_endpoint(), product_body(product_id=999), "text/plain")
        browser = StrategyBrowser([valid, later])

        result = browser.fetch(SEARCH_URL, 35_000)

        self.assertTrue(result["valid"])
        self.assertEqual(valid.text_calls, 1)
        self.assertEqual(later.text_calls, 0)

    def test_internal_wait_is_less_than_request_timeout(self):
        browser = StrategyBrowser(
            [FakeResponse(search_endpoint(), product_body(), "text/plain")]
        )

        browser.fetch(SEARCH_URL, request_timeout_ms=35_000)

        self.assertEqual(browser.temporary_page.expect_timeout, 30_000)
        self.assertLess(browser.temporary_page.expect_timeout, 35_000)

    def test_detail_requires_matching_nm_id(self):
        mismatch = FakeResponse(
            "https://www.wildberries.ru/__internal/u-card/cards/v4/detail?nm=123",
            product_body(product_id=123),
            "text/plain",
        )
        browser = StrategyBrowser([mismatch])

        with self.assertRaisesRegex(RuntimeError, "no valid matching response"):
            browser.fetch(DETAIL_URL, 35_000)

    def test_detail_text_plain_json_is_accepted_for_matching_nm_id(self):
        response = FakeResponse(
            "https://www.wildberries.ru/__internal/u-card/cards/v4/detail?nm=881219291",
            product_body(),
            "text/plain; charset=UTF-8",
        )
        browser = StrategyBrowser([response])

        result = browser.fetch(DETAIL_URL, 35_000)

        self.assertTrue(result["valid"])
        self.assertEqual(result["response_kind"], "detail")
        self.assertEqual(result["requested_nm_id"], "881219291")
        self.assertEqual(result["parsed_nm_id"], "881219291")

    def test_listener_and_page_are_cleaned_in_finally(self):
        browser = StrategyBrowser(
            [FakeResponse(search_endpoint(), "not json", "text/plain")]
        )

        with self.assertRaises(RuntimeError):
            browser.fetch(SEARCH_URL, 35_000)

        self.assertTrue(browser.temporary_page.listener_was_registered_before_goto)
        self.assertEqual(browser.temporary_page.listeners, [])
        self.assertTrue(browser.temporary_page.closed)


if __name__ == "__main__":
    unittest.main()
