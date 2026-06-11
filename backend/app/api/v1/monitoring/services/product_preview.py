from dataclasses import dataclass
from typing import Any

import httpx
from django.conf import settings

from app.core.logging import get_logger


logger = get_logger(__name__)


class ProductPreviewError(Exception):
    pass


@dataclass(frozen=True)
class ProductPreviewData:
    external_id: str
    title: str
    seller_name: str
    brand: str
    price: int | None
    old_price: int | None
    currency: str
    is_available: bool
    rating: float | None
    reviews_count: int | None
    raw_data: dict[str, Any]


class ProductPreviewService:
    def preview_product(
        self,
        *,
        marketplace: str,
        url: str,
    ) -> ProductPreviewData:
        client = ProductPreviewFetcherClient(
            base_url=settings.GO_FETCHER_BASE_URL,
            product_endpoint=settings.GO_FETCHER_PRODUCT_ENDPOINT,
            api_key=getattr(settings, "GO_FETCHER_API_KEY", ""),
            timeout_seconds=getattr(settings, "GO_FETCHER_TIMEOUT_SECONDS", 15),
        )

        return client.fetch_product_preview(
            marketplace=marketplace,
            url=url,
        )


class ProductPreviewFetcherClient:
    def __init__(
        self,
        *,
        base_url: str,
        product_endpoint: str,
        api_key: str,
        timeout_seconds: int,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.product_endpoint = product_endpoint
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def fetch_product_preview(
        self,
        *,
        marketplace: str,
        url: str,
    ) -> ProductPreviewData:
        endpoint = self._build_endpoint()

        payload = {
            "marketplace": marketplace,
            "url": url,
        }

        headers = {
            "Content-Type": "application/json",
        }

        if self.api_key:
            headers["X-Fetcher-Api-Key"] = self.api_key

        try:
            response = httpx.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()

        except httpx.TimeoutException as exc:
            logger.warning(
                "Product preview fetcher timeout",
                extra={
                    "service": "product_preview",
                    "marketplace": marketplace,
                    "url": url,
                    "error": str(exc),
                },
            )
            raise ProductPreviewError(
                "Не удалось получить товар: сервис парсинга не ответил вовремя."
            ) from exc

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Product preview fetcher returned HTTP error",
                extra={
                    "service": "product_preview",
                    "marketplace": marketplace,
                    "url": url,
                    "status_code": exc.response.status_code,
                    "response_text": exc.response.text,
                },
            )
            raise ProductPreviewError(
                "Не удалось получить товар. Проверьте ссылку или попробуйте позже."
            ) from exc

        except httpx.RequestError as exc:
            logger.warning(
                "Product preview fetcher request error",
                extra={
                    "service": "product_preview",
                    "marketplace": marketplace,
                    "url": url,
                    "error": str(exc),
                },
            )
            raise ProductPreviewError(
                "Сервис парсинга временно недоступен."
            ) from exc

        try:
            data = response.json()

        except ValueError as exc:
            logger.warning(
                "Product preview fetcher returned invalid JSON",
                extra={
                    "service": "product_preview",
                    "marketplace": marketplace,
                    "url": url,
                    "response_text": response.text,
                },
            )
            raise ProductPreviewError(
                "Сервис парсинга вернул некорректный ответ."
            ) from exc

        return self._parse_response(data=data)

    def _build_endpoint(self) -> str:
        product_endpoint = self.product_endpoint

        if not product_endpoint.startswith("/"):
            product_endpoint = f"/{product_endpoint}"

        return f"{self.base_url}{product_endpoint}"

    def _parse_response(self, *, data: dict[str, Any]) -> ProductPreviewData:
        product = data.get("product")

        if product is None:
            product = data

        external_id = self._as_str(
            product.get("external_id")
            or product.get("sku")
            or product.get("id")
        )
        title = self._as_str(product.get("title"))

        if not external_id:
            raise ProductPreviewError(
                "Товар найден, но сервис парсинга не вернул внешний идентификатор товара."
            )

        if not title:
            raise ProductPreviewError(
                "Товар найден, но сервис парсинга не вернул название товара."
            )

        return ProductPreviewData(
            external_id=external_id,
            title=title,
            seller_name=self._as_str(product.get("seller_name")),
            brand=self._as_str(product.get("brand")),
            price=self._as_optional_int(
                product.get("price")
                or product.get("price_cents")
            ),
            old_price=self._as_optional_int(
                product.get("old_price")
                or product.get("old_price_cents")
            ),
            currency=self._as_str(product.get("currency") or "RUB"),
            is_available=self._as_bool(
                product.get("is_available")
                if "is_available" in product
                else product.get("available", 0)
            ),
            rating=self._as_optional_float(product.get("rating")),
            reviews_count=self._as_optional_int(product.get("reviews_count")),
            raw_data=data,
        )

    def _as_str(self, value: Any) -> str:
        if value is None:
            return ""

        return str(value).strip()

    def _as_optional_int(self, value: Any) -> int | None:
        if value is None:
            return None

        if value == "":
            return None

        try:
            return int(value)

        except (TypeError, ValueError):
            return None

    def _as_optional_float(self, value: Any) -> float | None:
        if value is None:
            return None

        if value == "":
            return None

        try:
            return float(value)

        except (TypeError, ValueError):
            return None

    def _as_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value

        if isinstance(value, int):
            return value > 0

        if isinstance(value, str):
            return value.strip().lower() in {
                "true",
                "1",
                "yes",
                "available",
            }

        return bool(value)
