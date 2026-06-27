from dataclasses import dataclass
from typing import Any

from app.api.v1.notifications.services.channel_settings_service import (
    TelegramChannelNotFoundError,
    TelegramChannelValidationError,
    get_telegram_channel_settings,
    set_telegram_channel_active,
    toggle_telegram_channel_alert_type,
)
from app.api.v1.notifications.services.delivery_query_service import (
    DEFAULT_TELEGRAM_DELIVERY_HISTORY_LIMIT,
    get_telegram_delivery_history,
)
from app.api.v1.notifications.telegram.client import TelegramBotClient
from app.api.v1.notifications.telegram.keyboards import (
    NOTIFICATIONS_ACTIVE_CALLBACK_PREFIX,
    NOTIFICATIONS_HISTORY_CALLBACK_DATA,
    NOTIFICATIONS_OPEN_CALLBACK_DATA,
    NOTIFICATIONS_TYPE_CALLBACK_PREFIX,
    build_notification_delivery_history_keyboard,
    build_notification_settings_keyboard,
)
from app.api.v1.notifications.telegram.notifications_presenter import (
    build_notification_delivery_history_text,
    build_notification_settings_text,
)
from app.api.v1.notifications.telegram.replies import TelegramReplyService
from app.api.v1.notifications.telegram.target_alert_settings_presenter import (
    CALLBACK_CODE_TO_ALERT_TYPE,
)
from app.api.v1.notifications.telegram.target_callback import (
    extract_target_callback_envelope,
)
from app.api.v1.notifications.telegram.user_context import (
    TelegramUserContext,
    TelegramUserContextResolver,
)
from app.core.logging import get_logger


logger = get_logger(__name__)

MESSAGE_CALLBACK_EXPIRED = (
    "Это действие устарело. Откройте настройки командой /notifications."
)
MESSAGE_CALLBACK_FORBIDDEN = (
    "Это действие относится к другому пользователю."
)
MESSAGE_CONNECT_REQUIRED = "Telegram не подключён к аккаунту."
MESSAGE_SETTINGS_ERROR = "Не удалось изменить настройки уведомлений."


@dataclass(frozen=True, slots=True)
class ParsedNotificationsCallback:
    action: str
    desired_active: bool | None = None
    alert_type: str | None = None


class TelegramNotificationsHandler:
    def __init__(
        self,
        *,
        client: TelegramBotClient,
        replies: TelegramReplyService,
        user_context_resolver: TelegramUserContextResolver,
        delivery_history_limit: int = (
            DEFAULT_TELEGRAM_DELIVERY_HISTORY_LIMIT
        ),
    ) -> None:
        self.client = client
        self.replies = replies
        self.user_context_resolver = user_context_resolver
        self.delivery_history_limit = delivery_history_limit

    def handle_command(
        self,
        *,
        user_context: TelegramUserContext,
    ) -> None:
        try:
            settings = get_telegram_channel_settings(
                user=user_context.user,
                telegram_chat_id=(
                    user_context.telegram_chat_id
                ),
            )
        except TelegramChannelNotFoundError:
            self.replies.send_message(
                chat_id=user_context.telegram_chat_id,
                text=MESSAGE_CONNECT_REQUIRED,
            )
            return
        except Exception as exc:
            logger.exception(
                "Telegram notification settings loading failed",
                extra={
                    "service": "telegram_bot",
                    "user_id": str(user_context.user.pk),
                    "error": str(exc),
                },
            )
            self.replies.send_message(
                chat_id=user_context.telegram_chat_id,
                text="⚠️ Не удалось загрузить настройки уведомлений.",
            )
            return

        self.replies.send_message(
            chat_id=user_context.telegram_chat_id,
            text=build_notification_settings_text(
                settings=settings,
            ),
            reply_markup=build_notification_settings_keyboard(
                settings=settings,
            ),
        )

    def can_handle(
        self,
        *,
        callback_data: str,
    ) -> bool:
        return (
            callback_data == NOTIFICATIONS_OPEN_CALLBACK_DATA
            or callback_data == NOTIFICATIONS_HISTORY_CALLBACK_DATA
            or callback_data.startswith(
                NOTIFICATIONS_ACTIVE_CALLBACK_PREFIX
            )
            or callback_data.startswith(
                NOTIFICATIONS_TYPE_CALLBACK_PREFIX
            )
        )

    def handle(
        self,
        *,
        callback_query: dict[str, Any],
    ) -> None:
        envelope = extract_target_callback_envelope(
            callback_query=callback_query,
        )

        if envelope is None:
            callback_query_id = str(
                callback_query.get("id") or ""
            ).strip()

            if callback_query_id:
                self._answer_expired(callback_query_id)
            return

        if not envelope.belongs_to_chat_user:
            self.client.answer_callback_query(
                callback_query_id=envelope.callback_query_id,
                text=MESSAGE_CALLBACK_FORBIDDEN,
                show_alert=True,
            )
            return

        user_context = self.user_context_resolver.resolve(
            telegram_chat_id=envelope.chat_id,
        )

        if user_context is None:
            self.client.answer_callback_query(
                callback_query_id=envelope.callback_query_id,
                text=MESSAGE_CONNECT_REQUIRED,
                show_alert=True,
            )
            return

        parsed = self._parse_callback_data(
            callback_data=envelope.callback_data,
        )

        if parsed is None:
            self._answer_expired(envelope.callback_query_id)
            return

        if parsed.action == "history":
            self.client.answer_callback_query(
                callback_query_id=envelope.callback_query_id,
            )
            self._render_history(
                chat_id=envelope.chat_id,
                message_id=envelope.message_id,
                user_context=user_context,
            )
            return

        if parsed.action == "open":
            self.client.answer_callback_query(
                callback_query_id=envelope.callback_query_id,
            )
            self._render_settings(
                chat_id=envelope.chat_id,
                message_id=envelope.message_id,
                user_context=user_context,
            )
            return

        try:
            if parsed.action == "active":
                assert parsed.desired_active is not None
                settings = set_telegram_channel_active(
                    user=user_context.user,
                    telegram_chat_id=(
                        user_context.telegram_chat_id
                    ),
                    is_active=parsed.desired_active,
                )
                confirmation = (
                    "Все Telegram-уведомления включены."
                    if parsed.desired_active
                    else "Все Telegram-уведомления приостановлены."
                )
            else:
                assert parsed.alert_type is not None
                settings = toggle_telegram_channel_alert_type(
                    user=user_context.user,
                    telegram_chat_id=(
                        user_context.telegram_chat_id
                    ),
                    alert_type=parsed.alert_type,
                )
                confirmation = "Настройки типа уведомлений изменены."
        except TelegramChannelValidationError as exc:
            self.client.answer_callback_query(
                callback_query_id=envelope.callback_query_id,
                text=str(exc),
                show_alert=True,
            )
            return
        except TelegramChannelNotFoundError:
            self.client.answer_callback_query(
                callback_query_id=envelope.callback_query_id,
                text=MESSAGE_CONNECT_REQUIRED,
                show_alert=True,
            )
            return
        except Exception as exc:
            logger.exception(
                "Telegram notification settings update failed",
                extra={
                    "service": "telegram_bot",
                    "user_id": str(user_context.user.pk),
                    "action": parsed.action,
                    "error": str(exc),
                },
            )
            self.client.answer_callback_query(
                callback_query_id=envelope.callback_query_id,
                text=MESSAGE_SETTINGS_ERROR,
                show_alert=True,
            )
            return

        self.client.answer_callback_query(
            callback_query_id=envelope.callback_query_id,
            text=confirmation,
        )
        self.client.edit_message_text(
            chat_id=envelope.chat_id,
            message_id=envelope.message_id,
            text=build_notification_settings_text(
                settings=settings,
            ),
            reply_markup=build_notification_settings_keyboard(
                settings=settings,
            ),
        )

    def _render_settings(
        self,
        *,
        chat_id: str,
        message_id: int,
        user_context: TelegramUserContext,
    ) -> None:
        try:
            settings = get_telegram_channel_settings(
                user=user_context.user,
                telegram_chat_id=(
                    user_context.telegram_chat_id
                ),
            )
        except Exception as exc:
            logger.exception(
                "Telegram notification settings render failed",
                extra={
                    "service": "telegram_bot",
                    "user_id": str(user_context.user.pk),
                    "error": str(exc),
                },
            )
            self.client.send_message(
                chat_id=chat_id,
                text="⚠️ Не удалось загрузить настройки уведомлений.",
            )
            return

        self.client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=build_notification_settings_text(
                settings=settings,
            ),
            reply_markup=build_notification_settings_keyboard(
                settings=settings,
            ),
        )

    def _render_history(
        self,
        *,
        chat_id: str,
        message_id: int,
        user_context: TelegramUserContext,
    ) -> None:
        try:
            history = get_telegram_delivery_history(
                user=user_context.user,
                channel=user_context.channel,
                limit=self.delivery_history_limit,
            )
        except Exception as exc:
            logger.exception(
                "Telegram delivery history loading failed",
                extra={
                    "service": "telegram_bot",
                    "user_id": str(user_context.user.pk),
                    "channel_id": str(user_context.channel.pk),
                    "error": str(exc),
                },
            )
            self.client.send_message(
                chat_id=chat_id,
                text="⚠️ Не удалось загрузить историю доставок.",
            )
            return

        self.client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=build_notification_delivery_history_text(
                history=history,
            ),
            reply_markup=(
                build_notification_delivery_history_keyboard()
            ),
        )

    def _answer_expired(self, callback_query_id: str) -> None:
        self.client.answer_callback_query(
            callback_query_id=callback_query_id,
            text=MESSAGE_CALLBACK_EXPIRED,
            show_alert=True,
        )

    @staticmethod
    def _parse_callback_data(
        *,
        callback_data: str,
    ) -> ParsedNotificationsCallback | None:
        if callback_data == NOTIFICATIONS_OPEN_CALLBACK_DATA:
            return ParsedNotificationsCallback(action="open")

        if callback_data == NOTIFICATIONS_HISTORY_CALLBACK_DATA:
            return ParsedNotificationsCallback(action="history")

        if callback_data.startswith(
            NOTIFICATIONS_ACTIVE_CALLBACK_PREFIX
        ):
            raw_state = callback_data[
                len(NOTIFICATIONS_ACTIVE_CALLBACK_PREFIX):
            ]

            if raw_state not in {"0", "1"}:
                return None

            return ParsedNotificationsCallback(
                action="active",
                desired_active=raw_state == "1",
            )

        if callback_data.startswith(
            NOTIFICATIONS_TYPE_CALLBACK_PREFIX
        ):
            code = callback_data[
                len(NOTIFICATIONS_TYPE_CALLBACK_PREFIX):
            ]
            alert_type = CALLBACK_CODE_TO_ALERT_TYPE.get(code)

            if alert_type is None:
                return None

            return ParsedNotificationsCallback(
                action="type",
                alert_type=alert_type,
            )

        return None
