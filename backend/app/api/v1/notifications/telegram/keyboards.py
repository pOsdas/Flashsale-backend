from typing import Any

from app.api.v1.monitoring.models import MonitoringTargetStatus
from app.api.v1.monitoring.services.alert_rule_service import (
    EffectiveAlertRule,
)
from app.api.v1.monitoring.services.target_query_service import (
    MonitoringTargetPage,
)
from app.api.v1.notifications.telegram.target_alert_settings_presenter import (
    ALERT_TYPE_TO_CALLBACK_CODE,
    ALERT_TYPE_TITLES,
)
from app.api.v1.notifications.telegram.target_interval_presenter import (
    TELEGRAM_CHECK_INTERVAL_OPTIONS,
    format_interval_option,
)


PRODUCT_ADD_CALLBACK_PREFIX = "product:add:"
PRODUCT_CANCEL_CALLBACK_PREFIX = "product:cancel:"

PRODUCTS_PAGE_CALLBACK_PREFIX = "products:page:"
TARGET_CHECK_CALLBACK_PREFIX = "target:check:"
TARGET_PAUSE_CALLBACK_PREFIX = "target:pause:"
TARGET_RESUME_CALLBACK_PREFIX = "target:resume:"

# Kept for compatibility with buttons sent before the new settings screens.
TARGET_SETTINGS_CALLBACK_PREFIX = "target:settings:"

TARGET_DELETE_ASK_CALLBACK_PREFIX = "target:delete:ask:"
TARGET_DELETE_CONFIRM_CALLBACK_PREFIX = "target:delete:confirm:"
TARGET_DELETE_CANCEL_CALLBACK_PREFIX = "target:delete:cancel:"

TARGET_ALERTS_OPEN_CALLBACK_PREFIX = "ta:o:"
TARGET_ALERTS_SET_CALLBACK_PREFIX = "ta:s:"
TARGET_ALERTS_BACK_CALLBACK_PREFIX = "ta:b:"

TARGET_INTERVAL_OPEN_CALLBACK_PREFIX = "ti:o:"
TARGET_INTERVAL_SET_CALLBACK_PREFIX = "ti:s:"
TARGET_INTERVAL_BACK_CALLBACK_PREFIX = "ti:b:"

TARGET_HISTORY_OPEN_CALLBACK_PREFIX = "th:o:"
TARGET_HISTORY_BACK_CALLBACK_PREFIX = "th:b:"


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
                    "text": f"🔔 Уведомления {index}",
                    "callback_data": _build_target_callback_data(
                        prefix=TARGET_ALERTS_OPEN_CALLBACK_PREFIX,
                        target_id=target_id,
                        page=page,
                    ),
                },
                {
                    "text": f"⏱ Интервал {index}",
                    "callback_data": _build_target_callback_data(
                        prefix=TARGET_INTERVAL_OPEN_CALLBACK_PREFIX,
                        target_id=target_id,
                        page=page,
                    ),
                },
            ]
        )
        rows.append(
            [
                {
                    "text": f"📜 История {index}",
                    "callback_data": _build_target_callback_data(
                        prefix=TARGET_HISTORY_OPEN_CALLBACK_PREFIX,
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


def build_target_alert_settings_keyboard(
    *,
    target_id: str,
    page: int,
    rules: list[EffectiveAlertRule] | tuple[EffectiveAlertRule, ...],
) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []

    for rule in rules:
        code = ALERT_TYPE_TO_CALLBACK_CODE.get(rule.alert_type)

        if code is None:
            continue

        desired_state = not rule.is_enabled
        state = "✅" if rule.is_enabled else "❌"
        title = ALERT_TYPE_TITLES.get(
            rule.alert_type,
            rule.alert_type,
        )
        rows.append(
            [
                {
                    "text": f"{state} {title}",
                    "callback_data": (
                        f"{TARGET_ALERTS_SET_CALLBACK_PREFIX}"
                        f"{code}:{int(desired_state)}:"
                        f"{target_id}:{page}"
                    ),
                }
            ]
        )

    rows.append(
        [
            {
                "text": "⬅️ К товарам",
                "callback_data": _build_target_callback_data(
                    prefix=TARGET_ALERTS_BACK_CALLBACK_PREFIX,
                    target_id=target_id,
                    page=page,
                ),
            }
        ]
    )

    return {
        "inline_keyboard": rows,
    }


def build_target_interval_keyboard(
    *,
    target_id: str,
    page: int,
    current_interval_minutes: int,
) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    option_buttons: list[dict[str, str]] = []

    for minutes in TELEGRAM_CHECK_INTERVAL_OPTIONS:
        marker = "✅ " if minutes == current_interval_minutes else ""
        option_buttons.append(
            {
                "text": f"{marker}{format_interval_option(minutes)}",
                "callback_data": (
                    f"{TARGET_INTERVAL_SET_CALLBACK_PREFIX}"
                    f"{minutes}:{target_id}:{page}"
                ),
            }
        )

    for index in range(0, len(option_buttons), 2):
        rows.append(option_buttons[index:index + 2])

    rows.append(
        [
            {
                "text": "⬅️ К товарам",
                "callback_data": _build_target_callback_data(
                    prefix=TARGET_INTERVAL_BACK_CALLBACK_PREFIX,
                    target_id=target_id,
                    page=page,
                ),
            }
        ]
    )

    return {
        "inline_keyboard": rows,
    }


def build_target_history_keyboard(
    *,
    target_id: str,
    page: int,
) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "⬅️ К товарам",
                    "callback_data": _build_target_callback_data(
                        prefix=TARGET_HISTORY_BACK_CALLBACK_PREFIX,
                        target_id=target_id,
                        page=page,
                    ),
                }
            ],
        ]
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
