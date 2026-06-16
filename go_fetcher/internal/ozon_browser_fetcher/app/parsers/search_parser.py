from urllib.parse import urlencode

from playwright.sync_api import Page

from ozon_browser_fetcher.app.models.product import Product
from ozon_browser_fetcher.app.parsers.listing_parser import parse_listing_from_page


def build_search_url(query: str) -> str:
    query = query.strip()

    if not query:
        raise RuntimeError("search query is required")

    params = urlencode(
        {
            "text": query,
            "from_global": "true",
        }
    )

    return f"https://www.ozon.ru/search/?{params}"


def parse_search_from_page(page: Page, query: str, limit: int = 10) -> list[Product]:
    search_url = build_search_url(query)

    return parse_listing_from_page(
        page=page,
        url=search_url,
        limit=limit,
    )
