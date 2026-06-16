from playwright.sync_api import Page

from ozon_browser_fetcher.app.models.product import Product
from ozon_browser_fetcher.app.parsers.listing_parser import (
    normalize_ozon_url,
    parse_listing_from_page,
)


def normalize_category_url(url: str) -> str:
    url = url.strip()

    if not url:
        raise RuntimeError("category url is required")

    normalized_url = normalize_ozon_url(url)

    if "/category/" not in normalized_url:
        raise RuntimeError(f"invalid Ozon category url: {url}")

    return normalized_url


def parse_category_from_page(page: Page, url: str, limit: int = 10) -> list[Product]:
    category_url = normalize_category_url(url)

    return parse_listing_from_page(
        page=page,
        url=category_url,
        limit=limit,
    )
