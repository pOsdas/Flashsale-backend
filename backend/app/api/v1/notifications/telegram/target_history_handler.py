from typing import Any
from uuid import UUID

from app.api.v1.monitoring.services.target_history_service import (
    DEFAULT_TELEGRAM_TARGET_HISTORY_LIMIT,
    get_monitoring_target_history,
)
from app.api.v1.monitoring.services.target_service import (
    MonitoringTargetNotFoundError,
)
from app.api.v1.notifications.telegram.client import TelegramBotClient
from app.api.v1.notifications.telegram.keyboards import (
    TARGET_HISTORY_BACK_CALLBACK_PREFIX,
    TARGET_HISTORY_OPEN_CALLBACK_PREFIX,
    build_target_history_keyboard,
)
from app.api.v1.notifications.telegram.products_handler import (
    TelegramProductsHandler,
)
from app.api.v1.notifications.telegram.target_callback import (
    extract_target_callback_envelope,
    parse_target_and_page,
)
from app.api.v1.notifications.telegram.target_history_presenter import (
    build_target_history_text,
)
from app.api.v1.notifications.telegram.user_context import (
    TelegramUserContext,
    TelegramUserContextResolver,
)
from app.core.logging import get_logger


logger = get_logger(__name__)

MESSAGE_CALLBACK_EXPIRED = (
    "Это действие устарело. Откройте список заново командой /products."
)
MESSAGE_CALLBACK_FORBIDDEN = (
    "Это действие относится к другому пользователю."
)
MESSAGE_CONNECT_REQUIRED = "Telegram не подключён к аккаунту."
MESSAGE_TARGET_NOT_FOUND = "Товар не найден или уже был удалён."


class TelegramTargetHistoryHandler:
    def __init__(
        self,
        *,
        client: TelegramBotClient,
        user_context_resolver: TelegramUserContextResolver,
        products_handler: TelegramProductsHandler,
        history_limit: int = DEFAULT_TELEGRAM_TARGET_HISTORY_LIMIT,
    ) -> None:
        self.client = client
        self.user_context_resolver = user_context_resolver
        self.products_handler = products_handler
        self.history_limit = history_limit

    def can_handle(
        self,
        *,
        callback_data: str,
    ) -> bool:
        return callback_data.startswith(
            (
                TARGET_HISTORY_OPEN_CALLBACK_PREFIX,
                TARGET_HISTORY_BACK_CALLBACK_PREFIX,
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

        action, target_id, page = parsed

        if action == "back":
            self.client.answer_callback_query(
                callback_query_id=envelope.callback_query_id,
            )
            self.products_handler.edit_page(
                chat_id=envelope.chat_id,
                message_id=envelope.message_id,
                user_context=user_context,
                page=page,
            )
            return

        self.client.answer_callback_query(
            callback_query_id=envelope.callback_query_id,
        )
        self._render(
            chat_id=envelope.chat_id,
            message_id=envelope.message_id,
            user_context=user_context,
            target_id=target_id,
            page=page,
        )

    def _render(
        self,
        *,
        chat_id: str,
        message_id: int,
        user_context: TelegramUserContext,
        target_id: UUID,
        page: int,
    ) -> None:
        try:
            history = get_monitoring_target_history(
                user=user_context.user,
                target_id=target_id,
                limit=self.history_limit,
            )
        except MonitoringTargetNotFoundError:
            self.client.send_message(
                chat_id=chat_id,
                text=MESSAGE_TARGET_NOT_FOUND,
            )
            self.products_handler.edit_page(
                chat_id=chat_id,
                message_id=message_id,
                user_context=user_context,
                page=page,
            )
            return
        except Exception as exc:
            logger.exception(
                "Telegram target history loading failed",
                extra={
                    "service": "telegram_bot",
                    "user_id": str(user_context.user.pk),
                    "target_id": str(target_id),
                    "error": str(exc),
                },
            )
            self.client.send_message(
                chat_id=chat_id,
                text="⚠️ Не удалось загрузить историю товара.",
            )
            return

        self.client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=build_target_history_text(
                history=history,
            ),
            reply_markup=build_target_history_keyboard(
                target_id=str(history.target.id),
                page=page,
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
    ) -> tuple[str, UUID, int] | None:
        prefix_actions = (
            (TARGET_HISTORY_OPEN_CALLBACK_PREFIX, "open"),
            (TARGET_HISTORY_BACK_CALLBACK_PREFIX, "back"),
        )

        for prefix, action in prefix_actions:
            if not callback_data.startswith(prefix):
                continue

            parsed = parse_target_and_page(
                payload=callback_data[len(prefix):],
            )

            if parsed is None:
                return None

            target_id, page = parsed
            return action, target_id, page

        return None
