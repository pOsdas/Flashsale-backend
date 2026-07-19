import json
import threading
import unittest

from wb_browser_fetcher.app.browser import WBBrowser


DETAIL_URL = "https://www.wildberries.ru/__internal/u-card/cards/v4/detail?nm=881219291"
SEARCH_URL = "https://www.wildberries.ru/__internal/search/exactmatch/ru/common/v18/search?query=iphone"


class FakeResponse:
    def __init__(self, url, body, content_type="application/json", status=200):
        self.url = url
        self.status = status
        self.headers = {"content-type": content_type}
        self._body = body

    def text(self):
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
            raise TimeoutError("no matching response")


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
                if self.expectation.value is None:
                    self.expectation.value = response
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

    def is_ready(self):
        return True

    def _reload_cookies(self, force=False):
        return None


def product_body(container="products"):
    return json.dumps(
        {
            container: [
                {
                    "id": 881219291,
                    "name": "iPhone 17 Pro 512 GB",
                    "salePriceU": 14999000,
                    "totalQuantity": 1,
                }
            ]
        }
    )


class WBBrowserStrategyTests(unittest.TestCase):
    def test_search_opens_real_page_and_returns_intercepted_json(self):
        endpoint = "https://search.wb.ru/exactmatch/ru/common/v18/search?query=iphone"
        browser = StrategyBrowser([FakeResponse(endpoint, product_body())])

        result = browser.fetch(SEARCH_URL)

        self.assertEqual(
            browser.temporary_page.url,
            "https://www.wildberries.ru/catalog/0/search.aspx?search=iphone",
        )
        self.assertTrue(browser.temporary_page.listener_was_registered_before_goto)
        self.assertTrue(browser.temporary_page.closed)
        self.assertEqual(result["final_url"], endpoint)
        self.assertEqual(json.loads(result["body"])["products"][0]["id"], 881219291)

    def test_detail_opens_product_page_and_accepts_cards_json(self):
        endpoint = "https://www.wildberries.ru/__internal/card/cards/v4/detail?nm=881219291"
        browser = StrategyBrowser([FakeResponse(endpoint, product_body("cards"))])

        result = browser.fetch(DETAIL_URL)

        self.assertEqual(
            browser.temporary_page.url,
            "https://www.wildberries.ru/catalog/881219291/detail.aspx",
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["parsed_nm_id"], "881219291")
        self.assertTrue(browser.temporary_page.closed)

    def test_html_candidate_is_rejected_and_temporary_page_is_closed(self):
        endpoint = "https://www.wildberries.ru/__internal/search/catalog/search?query=iphone"
        browser = StrategyBrowser(
            [FakeResponse(endpoint, "<html>blocked</html>", "text/html")]
        )

        with self.assertRaisesRegex(RuntimeError, "Content-Type is not JSON"):
            browser.fetch(SEARCH_URL)

        self.assertTrue(browser.temporary_page.closed)


if __name__ == "__main__":
    unittest.main()
