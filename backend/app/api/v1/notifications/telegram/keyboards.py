from typing import Any


PRODUCT_ADD_CALLBACK_PREFIX = "product:add:"
PRODUCT_CANCEL_CALLBACK_PREFIX = "product:cancel:"


def build_product_preview_keyboard(
    *,
    token: str,
) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Добавить в отслеживание",
                    "callback_data": (
                        f"{PRODUCT_ADD_CALLBACK_PREFIX}{token}"
                    ),
                }
            ],
            [
                {
                    "text": "❌ Отмена",
                    "callback_data": (
                        f"{PRODUCT_CANCEL_CALLBACK_PREFIX}{token}"
                    ),
                }
            ],
        ]
    }


def build_empty_inline_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [],
    }
