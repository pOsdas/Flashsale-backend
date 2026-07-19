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


def analyze_response(
    body: str,
    content_type: str,
    requested_url: str,
) -> Dict[str, Any]:
    body_text = str(body or "")
    requested_nm = requested_nm_id(requested_url)
    lowered_content_type = str(content_type or "").lower()
    stripped = body_text.lstrip()
    response_kind = "html" if (
        "text/html" in lowered_content_type
        or stripped.startswith("<")
        or "<html" in stripped[:500].lower()
    ) else "unknown"

    try:
        payload = json.loads(body_text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {
            "valid": False,
            "error": "response body is not Wildberries JSON",
            "response_kind": response_kind,
            "requested_nm_id": requested_nm,
            "parsed_nm_id": "",
        }

    response_kind = "json"
    if not isinstance(payload, dict):
        return {
            "valid": False,
            "error": "Wildberries JSON payload is not an object",
            "response_kind": response_kind,
            "requested_nm_id": requested_nm,
            "parsed_nm_id": "",
        }

    products = _products(payload)
    if not products:
        return {
            "valid": False,
            "error": "Wildberries JSON payload does not contain products/cards",
            "response_kind": response_kind,
            "requested_nm_id": requested_nm,
            "parsed_nm_id": "",
        }

    if not requested_nm:
        return {
            "valid": True,
            "error": "",
            "response_kind": response_kind,
            "requested_nm_id": "",
            "parsed_nm_id": "",
        }

    parsed_nm = str(products[0].get("id") or "").strip() if products else ""
    matching = next(
        (product for product in products if str(product.get("id") or "").strip() == requested_nm),
        None,
    )
    if matching is None:
        return {
            "valid": False,
            "error": "Wildberries response does not contain the requested product",
            "response_kind": response_kind,
            "requested_nm_id": requested_nm,
            "parsed_nm_id": parsed_nm,
        }

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

    return {
        "valid": not error,
        "error": error,
        "response_kind": response_kind,
        "requested_nm_id": requested_nm,
        "parsed_nm_id": parsed_nm,
    }
