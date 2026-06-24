from django.test import SimpleTestCase

from app.api.v1.monitoring.models import Marketplace
from app.api.v1.monitoring.services.marketplace_url import (
    MarketplaceUrlError,
    resolve_marketplace_url,
)


class MarketplaceUrlResolverTests(SimpleTestCase):
    def test_resolves_wildberries_url_from_message(self) -> None:
        result = resolve_marketplace_url(
            text=(
                "Посмотри товар "
                "https://www.wildberries.ru/catalog/123/detail.aspx"
            )
        )

        self.assertEqual(
            result.marketplace,
            Marketplace.WILDBERRIES,
        )
        self.assertEqual(
            result.url,
            "https://www.wildberries.ru/catalog/123/detail.aspx",
        )

    def test_resolves_ozon_url_and_removes_fragment(self) -> None:
        result = resolve_marketplace_url(
            text="https://www.ozon.ru/product/test-123/?oos_search=false#reviews"
        )

        self.assertEqual(
            result.marketplace,
            Marketplace.OZON,
        )
        self.assertEqual(
            result.url,
            "https://www.ozon.ru/product/test-123/?oos_search=false",
        )

    def test_rejects_unsupported_domain(self) -> None:
        with self.assertRaisesMessage(
            MarketplaceUrlError,
            "Поддерживаются только ссылки Wildberries и Ozon.",
        ):
            resolve_marketplace_url(
                text="https://example.com/product/123"
            )
