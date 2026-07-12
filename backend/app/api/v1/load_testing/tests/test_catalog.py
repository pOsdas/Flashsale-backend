from django.test import SimpleTestCase

from app.api.v1.load_testing.catalog import (
    build_synthetic_product,
    product_index_for_target,
)


class SyntheticCatalogTests(SimpleTestCase):
    def test_generated_urls_pass_marketplace_domain_validation(self):
        wb = build_synthetic_product(2)
        ozon = build_synthetic_product(3)

        self.assertEqual(wb.marketplace, "wb")
        self.assertIn("wildberries", wb.url)
        self.assertEqual(ozon.marketplace, "ozon")
        self.assertIn("ozon", ozon.url)

    def test_hot_targets_reuse_small_product_set(self):
        indexes = {
            product_index_for_target(
                target_index=index,
                total_targets=1000,
                popular_products=100,
                medium_products=200,
            )
            for index in range(500)
        }

        self.assertEqual(len(indexes), 100)
