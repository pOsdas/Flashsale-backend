from typing import Any


KNOWN_MARKETPLACE_LABELS = {
    "wb",
    "ozon",
}


def normalize_marketplace_label(value: Any) -> str:
    normalized = str(value or "").strip().lower()

    if normalized in KNOWN_MARKETPLACE_LABELS:
        return normalized

    return "unknown"


def build_http_status_class(status_code: int | None) -> str:
    if status_code is None:
        return "none"

    if 100 <= status_code <= 599:
        return f"{status_code // 100}xx"

    return "other"
