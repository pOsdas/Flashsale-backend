import json
import threading
import unittest

from wb_browser_fetcher.app.browser import WBBrowser


DETAIL_URL = "https://www.wildberries.ru/__internal/u-card/cards/v4/detail?nm=881219291"


class FakePage:
    def title(self):
        return "Смартфон iPhone 17 Pro 512 ГБ"


class StrategyBrowser(WBBrowser):
    def __init__(self):
        self.lock = threading.Lock()
        self.page = FakePage()
        self.context = object()
        self.direct_calls = 0
        self.alternative_calls = 0

    def is_ready(self):
        return True

    def _reload_cookies(self, force=False):
        return None

    def _fetch_once(self, url):
        self.direct_calls += 1
        return {
            "status_code": 200,
            "body": "<html><title>Интернет-магазин Wildberries</title></html>",
            "final_url": "https://www.wildberries.ru/",
            "content_type": "text/html",
        }

    def _prepare_page_for_request(self, url):
        self.alternative_calls += 1
        return {
            "status_code": 200,
            "body": json.dumps(
                {
                    "products": [
                        {
                            "id": 881219291,
                            "name": "Смартфон iPhone 17 Pro 512 ГБ",
                            "salePriceU": 14999000,
                            "totalQuantity": 1,
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            "final_url": "https://www.wildberries.ru/catalog/881219291/detail.aspx",
            "content_type": "application/json",
        }


class WBBrowserStrategyTests(unittest.TestCase):
    def test_invalid_direct_result_uses_valid_product_page_alternative(self):
        browser = StrategyBrowser()

        result = browser.fetch(DETAIL_URL)

        self.assertEqual(browser.direct_calls, 1)
        self.assertEqual(browser.alternative_calls, 1)
        self.assertTrue(result["valid"])
        self.assertEqual(result["parsed_nm_id"], "881219291")
        self.assertGreater(result["response_size"], 0)


if __name__ == "__main__":
    unittest.main()
