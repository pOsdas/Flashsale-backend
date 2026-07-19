import json
import unittest

from wb_browser_fetcher.app.validation import analyze_response, is_generic_title


DETAIL_URL = "https://www.wildberries.ru/__internal/u-card/cards/v4/detail?nm=881219291"
SEARCH_URL = "https://www.wildberries.ru/__internal/search/exactmatch/ru/common/v18/search?query=iphone&resultset=catalog"


def product_body(**overrides):
    product = {
        "id": 881219291,
        "name": "Смартфон iPhone 17 Pro 512 ГБ",
        "salePriceU": 14999000,
        "totalQuantity": 3,
    }
    product.update(overrides)
    return json.dumps({"products": [product]}, ensure_ascii=False)


class WBResponseValidationTests(unittest.TestCase):
    def test_accepts_real_product_json(self):
        result = analyze_response(product_body(), "application/json", DETAIL_URL)
        self.assertTrue(result["valid"])
        self.assertEqual(result["parsed_nm_id"], "881219291")

    def test_accepts_json_served_as_text_plain(self):
        result = analyze_response(
            product_body(),
            "text/plain; charset=UTF-8",
            DETAIL_URL,
            DETAIL_URL,
        )
        self.assertTrue(result["valid"])
        self.assertTrue(result["json_decode_success"])

    def test_rejects_generic_homepage_html(self):
        result = analyze_response(
            "<html><title>Интернет-магазин Wildberries: широкий ассортимент товаров - скидки каждый день!</title></html>",
            "text/html; charset=utf-8",
            DETAIL_URL,
        )
        self.assertFalse(result["valid"])
        self.assertEqual(result["response_kind"], "html")

    def test_rejects_http_200_non_product_json(self):
        result = analyze_response(json.dumps({"state": "ok"}), "application/json", DETAIL_URL)
        self.assertFalse(result["valid"])

    def test_rejects_filters_resultset_for_search(self):
        result = analyze_response(
            product_body(),
            "text/plain",
            SEARCH_URL,
            SEARCH_URL.replace("resultset=catalog", "resultset=filters"),
        )
        self.assertFalse(result["valid"])
        self.assertEqual(result["response_kind"], "search_filters")

    def test_accepts_catalog_resultset_for_search(self):
        result = analyze_response(
            product_body(),
            "text/plain",
            SEARCH_URL,
            SEARCH_URL,
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["response_kind"], "search_catalog")

    def test_accepts_cards_container(self):
        body = json.dumps({"cards": json.loads(product_body())["products"]})
        result = analyze_response(body, "application/json", DETAIL_URL)
        self.assertTrue(result["valid"])

    def test_rejects_different_nm_id(self):
        result = analyze_response(product_body(id=123), "application/json", DETAIL_URL)
        self.assertFalse(result["valid"])
        self.assertEqual(result["parsed_nm_id"], "123")

    def test_rejects_zero_price_for_available_product(self):
        result = analyze_response(product_body(salePriceU=0), "application/json", DETAIL_URL)
        self.assertFalse(result["valid"])
        self.assertIn("price", result["error"])

    def test_normalizes_generic_title_case_spaces_and_dashes(self):
        self.assertTrue(is_generic_title("  ИНТЕРНЕТ—МАГАЗИН   Wildberries: скидки каждый день! "))


if __name__ == "__main__":
    unittest.main()
