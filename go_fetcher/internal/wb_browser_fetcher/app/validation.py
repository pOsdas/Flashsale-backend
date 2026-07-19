import json
import re
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse


GENERIC_TITLE_PATTERNS = (
    "интернет магазин wildberries",
    "широкий ассортимент товаров",
    "скидки каждый день",
    "модный интернет магазин wildberries",
    "wildberries интернет магазин",
)


def normalize_title(value: str) -> str:
    normalized = str(value or "").strip().lower()
    normalized = re.sub(r"[-‐‑‒–—―\s]+", " ", normalized)
    return normalized.strip()


def is_generic_title(value: str) -> bool:
    normalized = normalize_title(value)
    return any(pattern in normalized for pattern in GENERIC_TITLE_PATTERNS)


def requested_nm_id(requested_url: str) -> str:
    parsed = urlparse(str(requested_url or ""))
    if "/card/" not in parsed.path and "/u-card/" not in parsed.path:
        return ""
    return str((parse_qs(parsed.query).get("nm") or [""])[0]).strip()


def _products(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("products", "cards"):
        products = payload.get(key)
        if isinstance(products, list):
            return [item for item in products if isinstance(item, dict)]
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("products", "cards"):
            products = data.get(key)
            if isinstance(products, list):
                return [item for item in products if isinstance(item, dict)]
    return []


def _price(product: Dict[str, Any]) -> int:
    for key in ("salePriceU", "priceU"):
        try:
            value = int(product.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value

    sizes = product.get("sizes")
    if isinstance(sizes, list):
        for size in sizes:
            price = size.get("price") if isinstance(size, dict) else None
            if not isinstance(price, dict):
                continue
            for key in ("product", "total", "basic"):
                try:
                    value = int(price.get(key) or 0)
                except (TypeError, ValueError):
                    value = 0
                if value > 0:
                    return value
    return 0


def _valid_catalog_products(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    valid_products: List[Dict[str, Any]] = []
    for product in products:
        product_id = str(product.get("id") or "").strip()
        title = str(product.get("name") or product.get("brand") or "").strip()
        if product_id.isdigit() and int(product_id) > 0 and title:
            valid_products.append(product)
    return valid_products


def _analysis_result(
    *,
    valid: bool,
    error: str,
    response_kind: str,
    requested_nm_id_value: str,
    parsed_nm_id: str = "",
    json_decode_success: bool = False,
    resultset: str = "",
    products_count: int = 0,
) -> Dict[str, Any]:
    return {
        "valid": valid,
        "error": error,
        "response_kind": response_kind,
        "requested_nm_id": requested_nm_id_value,
        "parsed_nm_id": parsed_nm_id,
        "json_decode_success": json_decode_success,
        "resultset": resultset,
        "products_count": products_count,
    }


def analyze_response(
    body: str,
    content_type: str,
    requested_url: str,
    response_url: str = "",
) -> Dict[str, Any]:
    body_text = str(body or "")
    requested_nm = requested_nm_id(requested_url)
    requested_path = urlparse(str(requested_url or "")).path
    is_search = "/search/" in requested_path and not requested_nm
    lowered_content_type = str(content_type or "").lower()
    stripped = body_text.lstrip()
    is_html = (
        "text/html" in lowered_content_type
        or stripped.startswith("<")
        or "<html" in stripped[:500].lower()
    )
    response_query = parse_qs(urlparse(str(response_url or "")).query)
    requested_query = parse_qs(urlparse(str(requested_url or "")).query)
    resultset = str(
        (
            response_query.get("resultset")
            or requested_query.get("resultset")
            or [""]
        )[0]
    ).strip().lower()

    try:
        payload = json.loads(body_text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return _analysis_result(
            valid=False,
            error="response body is HTML, not Wildberries JSON" if is_html else "response body is not Wildberries JSON",
            response_kind="html" if is_html else "invalid_text",
            requested_nm_id_value=requested_nm,
            resultset=resultset,
        )

    if not isinstance(payload, dict):
        return _analysis_result(
            valid=False,
            error="Wildberries JSON payload is not an object",
            response_kind="invalid_json",
            requested_nm_id_value=requested_nm,
            json_decode_success=True,
            resultset=resultset,
        )

    products = _products(payload)
    products_count = len(products)
    if is_search:
        if resultset == "filters":
            return _analysis_result(
                valid=False,
                error="Wildberries search response resultset=filters is not a product catalog",
                response_kind="search_filters",
                requested_nm_id_value="",
                json_decode_success=True,
                resultset=resultset,
                products_count=products_count,
            )
        if resultset and resultset != "catalog":
            return _analysis_result(
                valid=False,
                error=f"Wildberries search response resultset={resultset} is not the preferred product catalog",
                response_kind="search_non_catalog",
                requested_nm_id_value="",
                json_decode_success=True,
                resultset=resultset,
                products_count=products_count,
            )
        valid_products = _valid_catalog_products(products)
        if not valid_products:
            return _analysis_result(
                valid=False,
                error="Wildberries search JSON does not contain a valid product catalog",
                response_kind="search_catalog_invalid",
                requested_nm_id_value="",
                json_decode_success=True,
                resultset=resultset,
                products_count=products_count,
            )
        return _analysis_result(
            valid=True,
            error="",
            response_kind="search_catalog",
            requested_nm_id_value="",
            json_decode_success=True,
            resultset=resultset,
            products_count=len(valid_products),
        )

    if not products:
        return _analysis_result(
            valid=False,
            error="Wildberries JSON payload does not contain products/cards",
            response_kind="detail_invalid" if requested_nm else "marketplace_json_invalid",
            requested_nm_id_value=requested_nm,
            json_decode_success=True,
            resultset=resultset,
            products_count=0,
        )

    if not requested_nm:
        return _analysis_result(
            valid=True,
            error="",
            response_kind="marketplace_json",
            requested_nm_id_value="",
            json_decode_success=True,
            resultset=resultset,
            products_count=products_count,
        )

    parsed_nm = str(products[0].get("id") or "").strip() if products else ""
    matching = next(
        (product for product in products if str(product.get("id") or "").strip() == requested_nm),
        None,
    )
    if matching is None:
        return _analysis_result(
            valid=False,
            error="Wildberries response does not contain the requested product",
            response_kind="detail_invalid",
            requested_nm_id_value=requested_nm,
            parsed_nm_id=parsed_nm,
            json_decode_success=True,
            resultset=resultset,
            products_count=products_count,
        )

    parsed_nm = requested_nm
    title = str(matching.get("name") or "").strip()
    if not title:
        error = "Wildberries product title is empty"
    elif is_generic_title(title):
        error = "Wildberries product title is a generic marketplace title"
    else:
        try:
            available = int(matching.get("totalQuantity") or 0) > 0
        except (TypeError, ValueError):
            available = False
        error = "Wildberries available product price is empty or zero" if available and _price(matching) <= 0 else ""

    return _analysis_result(
        valid=not error,
        error=error,
        response_kind="detail" if not error else "detail_invalid",
        requested_nm_id_value=requested_nm,
        parsed_nm_id=parsed_nm,
        json_decode_success=True,
        resultset=resultset,
        products_count=products_count,
    )
