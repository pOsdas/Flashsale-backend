from typing import Any

from app.api.v1.monitoring.models import MonitoringTargetStatus
from app.api.v1.monitoring.services.target_query_service import (
    MonitoringTargetPage,
)


PRODUCT_ADD_CALLBACK_PREFIX = "product:add:"
PRODUCT_CANCEL_CALLBACK_PREFIX = "product:cancel:"

PRODUCTS_PAGE_CALLBACK_PREFIX = "products:page:"
TARGET_CHECK_CALLBACK_PREFIX = "target:check:"
TARGET_PAUSE_CALLBACK_PREFIX = "target:pause:"
TARGET_RESUME_CALLBACK_PREFIX = "target:resume:"
TARGET_SETTINGS_CALLBACK_PREFIX = "target:settings:"
TARGET_DELETE_ASK_CALLBACK_PREFIX = "target:delete:ask:"
TARGET_DELETE_CONFIRM_CALLBACK_PREFIX = "target:delete:confirm:"
TARGET_DELETE_CANCEL_CALLBACK_PREFIX = "target:delete:cancel:"


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


def build_products_keyboard(
    *,
    target_page: MonitoringTargetPage,
) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    start_number = (
        (target_page.page - 1) * target_page.page_size
    )

    for index, item in enumerate(
        target_page.items,
        start=start_number + 1,
    ):
        target = item.target
        target_id = str(target.id)
        page = target_page.page

        rows.append(
            [
                {
                    "text": f"🔄 Проверить {index}",
                    "callback_data": _build_target_callback_data(
                        prefix=TARGET_CHECK_CALLBACK_PREFIX,
                        target_id=target_id,
                        page=page,
                    ),
                },
                _build_target_activity_button(
                    target=target,
                    index=index,
                    page=page,
                ),
            ]
        )
        rows.append(
            [
                {
                    "text": f"⚙️ Настройки {index}",
                    "callback_data": _build_target_callback_data(
                        prefix=TARGET_SETTINGS_CALLBACK_PREFIX,
                        target_id=target_id,
                        page=page,
                    ),
                },
                {
                    "text": f"🗑 Удалить {index}",
                    "callback_data": _build_target_callback_data(
                        prefix=TARGET_DELETE_ASK_CALLBACK_PREFIX,
                        target_id=target_id,
                        page=page,
                    ),
                },
            ]
        )

    navigation_row: list[dict[str, str]] = []

    if target_page.has_previous:
        navigation_row.append(
            {
                "text": "⬅️ Назад",
                "callback_data": (
                    f"{PRODUCTS_PAGE_CALLBACK_PREFIX}"
                    f"{target_page.page - 1}"
                ),
            }
        )

    if target_page.has_next:
        navigation_row.append(
            {
                "text": "Вперёд ➡️",
                "callback_data": (
                    f"{PRODUCTS_PAGE_CALLBACK_PREFIX}"
                    f"{target_page.page + 1}"
                ),
            }
        )

    if navigation_row:
        rows.append(navigation_row)

    return {
        "inline_keyboard": rows,
    }


def build_target_delete_confirmation_keyboard(
    *,
    target_id: str,
    page: int,
) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Да, удалить",
                    "callback_data": _build_target_callback_data(
                        prefix=TARGET_DELETE_CONFIRM_CALLBACK_PREFIX,
                        target_id=target_id,
                        page=page,
                    ),
                },
                {
                    "text": "❌ Отмена",
                    "callback_data": _build_target_callback_data(
                        prefix=TARGET_DELETE_CANCEL_CALLBACK_PREFIX,
                        target_id=target_id,
                        page=page,
                    ),
                },
            ]
        ]
    }


def build_empty_inline_keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [],
    }


def _build_target_activity_button(
    *,
    target,
    index: int,
    page: int,
) -> dict[str, str]:
    target_id = str(target.id)

    if (
        target.status == MonitoringTargetStatus.ACTIVE
        and target.is_active
    ):
        return {
            "text": f"⏸ Пауза {index}",
            "callback_data": _build_target_callback_data(
                prefix=TARGET_PAUSE_CALLBACK_PREFIX,
                target_id=target_id,
                page=page,
            ),
        }

    return {
        "text": f"▶️ Возобновить {index}",
        "callback_data": _build_target_callback_data(
            prefix=TARGET_RESUME_CALLBACK_PREFIX,
            target_id=target_id,
            page=page,
        ),
    }


def _build_target_callback_data(
    *,
    prefix: str,
    target_id: str,
    page: int,
) -> str:
    return f"{prefix}{target_id}:{page}"
