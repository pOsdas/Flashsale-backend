from django.test import TestCase

from app.api.v1.catalog.exceptions import (
    InvalidProductDataError,
    ProductAlreadyExistsError,
    ProductNotFoundError,
)
from app.api.v1.catalog.models import Stock
from app.api.v1.catalog.selectors import (
    Pagination,
    ProductListFilters,
    get_product_by_id,
    get_product_by_sku,
    list_products,
)
from app.api.v1.catalog.services import create_product, set_stock


class CatalogServiceTests(TestCase):
    def setUp(self):
        self.product_1 = create_product(
            product_sku="TSHIRT-BLACK-S",
            title="Black T-Shirt Small",
            price_cents=1000,
            is_active=True,
            available=1,
        )

        self.product_2 = create_product(
            product_sku="IPHONE-17-PRO-MAX",
            title="iPhone 17 Pro Max",
            price_cents=1500,
            is_active=True,
            available=154,
        )

        self.inactive_product = create_product(
            product_sku="TSHIRT-BLACK-M",
            title="Black T-Shirt Medium",
            price_cents=2500,
            is_active=False,
            available=0,
        )

    def test_create_product_success(self):
        product = create_product(
            product_sku="MACBOOK-PRO-16",
            title="MacBook Pro 16",
            price_cents=2999,
            is_active=True,
            available=7,
        )

        self.assertEqual(product.sku, "MACBOOK-PRO-16")
        self.assertEqual(product.title, "MacBook Pro 16")
        self.assertEqual(product.price_cents, 2999)
        self.assertEqual(product.currency, "EUR")
        self.assertTrue(product.is_active)
        self.assertEqual(product.stock.available, 7)

    def test_list_products_returns_active_products_by_default(self):
        products = list(list_products())

        self.assertEqual(len(products), 2)
        self.assertTrue(all(product.is_active for product in products))

    def test_list_products_with_active_filter(self):
        products = list(
            list_products(filters=ProductListFilters(is_active=True))
        )

        self.assertEqual(len(products), 2)
        self.assertTrue(all(product.is_active for product in products))

    def test_list_products_with_inactive_filter(self):
        products = list(
            list_products(filters=ProductListFilters(is_active=False))
        )

        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].sku, "TSHIRT-BLACK-M")
        self.assertFalse(products[0].is_active)

    def test_list_products_with_search(self):
        products = list(
            list_products(filters=ProductListFilters(search="iphone"))
        )

        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].sku, "IPHONE-17-PRO-MAX")

    def test_list_products_with_pagination_limit(self):
        products = list(
            list_products(pagination=Pagination(limit=2))
        )

        self.assertEqual(len(products), 2)

    def test_list_products_with_pagination_offset(self):
        products = list(
            list_products(
                filters=ProductListFilters(is_active=None),
                pagination=Pagination(limit=10, offset=2),
            )
        )

        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].sku, "TSHIRT-BLACK-M")

    def test_get_product_by_sku_success(self):
        product = get_product_by_sku(
            product_sku="TSHIRT-BLACK-S",
        )

        self.assertEqual(product.id, self.product_1.id)
        self.assertEqual(product.sku, "TSHIRT-BLACK-S")

    def test_get_product_by_sku_raises_error_when_product_does_not_exist(self):
        with self.assertRaises(ProductNotFoundError) as ctx:
            get_product_by_sku(product_sku="ABRACADABRA")

        self.assertIn("ABRACADABRA", str(ctx.exception))

    def test_get_product_by_sku_raises_error_for_inactive_product_by_default(self):
        with self.assertRaises(ProductNotFoundError) as ctx:
            get_product_by_sku(product_sku="TSHIRT-BLACK-M")

        self.assertIn("TSHIRT-BLACK-M", str(ctx.exception))

    def test_get_product_by_sku_can_return_inactive_product_when_allowed(self):
        product = get_product_by_sku(
            product_sku="TSHIRT-BLACK-M",
            only_active=False,
        )

        self.assertEqual(product.id, self.inactive_product.id)
        self.assertFalse(product.is_active)

    def test_get_product_by_id_success(self):
        product = get_product_by_id(product_id=self.product_2.id)

        self.assertEqual(product.id, self.product_2.id)
        self.assertEqual(product.sku, "IPHONE-17-PRO-MAX")

    def test_get_product_by_id_raises_error_when_product_does_not_exist(self):
        with self.assertRaises(ProductNotFoundError) as ctx:
            get_product_by_id(product_id=999999)

        self.assertIn("999999", str(ctx.exception))

    def test_create_product_with_existing_sku_raises_error(self):
        with self.assertRaises(ProductAlreadyExistsError) as ctx:
            create_product(
                product_sku="TSHIRT-BLACK-S",
                title="Duplicate Product",
                price_cents=1000,
                is_active=True,
                available=1,
            )

        self.assertIn("TSHIRT-BLACK-S", str(ctx.exception))

    def test_create_product_with_negative_price_raises_error(self):
        with self.assertRaises(InvalidProductDataError) as ctx:
            create_product(
                product_sku="BAD-PRICE-001",
                title="Bad Price Product",
                price_cents=-100,
                is_active=True,
                available=1,
            )

        self.assertIn("Цена товара должна быть больше нуля", str(ctx.exception))

    def test_create_product_with_zero_price_raises_error(self):
        with self.assertRaises(InvalidProductDataError) as ctx:
            create_product(
                product_sku="ZERO-PRICE-001",
                title="Zero Price Product",
                price_cents=0,
                is_active=True,
                available=1,
            )

        self.assertIn("Цена товара должна быть больше нуля", str(ctx.exception))

    def test_create_product_with_negative_stock_raises_error(self):
        with self.assertRaises(InvalidProductDataError) as ctx:
            create_product(
                product_sku="BAD-STOCK-001",
                title="Bad Stock Product",
                price_cents=1000,
                is_active=True,
                available=-5,
            )

        self.assertIn("Количество товара не может быть отрицательным", str(ctx.exception))

    def test_set_stock_success(self):
        product = set_stock(
            product_sku="TSHIRT-BLACK-S",
            available=25,
        )

        self.assertEqual(product.sku, "TSHIRT-BLACK-S")
        self.assertEqual(product.stock.available, 25)

        stock = Stock.objects.get(product=self.product_1)
        self.assertEqual(stock.available, 25)

    def test_set_stock_with_unknown_sku_raises_error(self):
        with self.assertRaises(ProductNotFoundError) as ctx:
            set_stock(
                product_sku="UNKNOWN-SKU",
                available=10,
            )

        self.assertIn("UNKNOWN-SKU", str(ctx.exception))

    def test_set_stock_with_negative_available_raises_error(self):
        with self.assertRaises(InvalidProductDataError) as ctx:
            set_stock(
                product_sku="TSHIRT-BLACK-S",
                available=-1,
            )

        self.assertIn("Количество товара не может быть отрицательным", str(ctx.exception))
