from typing import Any
from uuid import UUID

from app.api.v1.monitoring.services.target_service import (
    MonitoringTargetNotFoundError,
    MonitoringTargetUpdateError,
    get_monitoring_target_for_user,
    update_monitoring_target,
)
from app.api.v1.notifications.telegram.client import TelegramBotClient
from app.api.v1.notifications.telegram.keyboards import (
    TARGET_INTERVAL_BACK_CALLBACK_PREFIX,
    TARGET_INTERVAL_OPEN_CALLBACK_PREFIX,
    TARGET_INTERVAL_SET_CALLBACK_PREFIX,
    build_target_interval_keyboard,
)
from app.api.v1.notifications.telegram.products_handler import (
    TelegramProductsHandler,
)
from app.api.v1.notifications.telegram.target_callback import (
    extract_target_callback_envelope,
    parse_target_and_page,
)
from app.api.v1.notifications.telegram.target_interval_presenter import (
    TELEGRAM_CHECK_INTERVAL_OPTIONS,
    build_target_interval_text,
    format_interval_option,
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


class TelegramTargetIntervalHandler:
    def __init__(
        self,
        *,
        client: TelegramBotClient,
        user_context_resolver: TelegramUserContextResolver,
        products_handler: TelegramProductsHandler,
    ) -> None:
        self.client = client
        self.user_context_resolver = user_context_resolver
        self.products_handler = products_handler

    def can_handle(
        self,
        *,
        callback_data: str,
    ) -> bool:
        return callback_data.startswith(
            (
                TARGET_INTERVAL_OPEN_CALLBACK_PREFIX,
                TARGET_INTERVAL_SET_CALLBACK_PREFIX,
                TARGET_INTERVAL_BACK_CALLBACK_PREFIX,
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

        action, target_id, page, interval_minutes = parsed

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

        if action == "set":
            assert interval_minutes is not None

            try:
                current_target = get_monitoring_target_for_user(
                    user=user_context.user,
                    target_id=target_id,
                )

                if (
                    current_target.check_interval_minutes
                    == interval_minutes
                ):
                    self.client.answer_callback_query(
                        callback_query_id=envelope.callback_query_id,
                        text="Этот интервал уже установлен.",
                    )
                    return

                update_monitoring_target(
                    user=user_context.user,
                    target_id=target_id,
                    validated_data={
                        "check_interval_minutes": interval_minutes,
                    },
                )
            except MonitoringTargetNotFoundError:
                self._answer_not_found(
                    callback_query_id=envelope.callback_query_id,
                    chat_id=envelope.chat_id,
                    message_id=envelope.message_id,
                    user_context=user_context,
                    page=page,
                )
                return
            except MonitoringTargetUpdateError as exc:
                self.client.answer_callback_query(
                    callback_query_id=envelope.callback_query_id,
                    text=str(exc),
                    show_alert=True,
                )
                return
            except Exception as exc:
                logger.exception(
                    "Telegram target interval update failed",
                    extra={
                        "service": "telegram_bot",
                        "user_id": str(user_context.user.pk),
                        "target_id": str(target_id),
                        "interval_minutes": interval_minutes,
                        "error": str(exc),
                    },
                )
                self.client.answer_callback_query(
                    callback_query_id=envelope.callback_query_id,
                    text="Не удалось изменить интервал проверки.",
                    show_alert=True,
                )
                return

            self.client.answer_callback_query(
                callback_query_id=envelope.callback_query_id,
                text=(
                    "Интервал изменён: "
                    f"{format_interval_option(interval_minutes)}."
                ),
            )
        else:
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
            target = get_monitoring_target_for_user(
                user=user_context.user,
                target_id=target_id,
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

        self.client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=build_target_interval_text(
                target=target,
            ),
            reply_markup=build_target_interval_keyboard(
                target_id=str(target.id),
                page=page,
                current_interval_minutes=target.check_interval_minutes,
            ),
        )

    def _answer_not_found(
        self,
        *,
        callback_query_id: str,
        chat_id: str,
        message_id: int,
        user_context: TelegramUserContext,
        page: int,
    ) -> None:
        self.client.answer_callback_query(
            callback_query_id=callback_query_id,
            text=MESSAGE_TARGET_NOT_FOUND,
            show_alert=True,
        )
        self.products_handler.edit_page(
            chat_id=chat_id,
            message_id=message_id,
            user_context=user_context,
            page=page,
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
    ) -> tuple[str, UUID, int, int | None] | None:
        if callback_data.startswith(TARGET_INTERVAL_OPEN_CALLBACK_PREFIX):
            parsed = parse_target_and_page(
                payload=callback_data[
                    len(TARGET_INTERVAL_OPEN_CALLBACK_PREFIX):
                ],
            )

            if parsed is None:
                return None

            target_id, page = parsed
            return "open", target_id, page, None

        if callback_data.startswith(TARGET_INTERVAL_BACK_CALLBACK_PREFIX):
            parsed = parse_target_and_page(
                payload=callback_data[
                    len(TARGET_INTERVAL_BACK_CALLBACK_PREFIX):
                ],
            )

            if parsed is None:
                return None

            target_id, page = parsed
            return "back", target_id, page, None

        if callback_data.startswith(TARGET_INTERVAL_SET_CALLBACK_PREFIX):
            payload = callback_data[
                len(TARGET_INTERVAL_SET_CALLBACK_PREFIX):
            ]

            try:
                interval_raw, target_and_page = payload.split(
                    ":",
                    maxsplit=1,
                )
                interval_minutes = int(interval_raw)
            except (TypeError, ValueError):
                return None

            if interval_minutes not in TELEGRAM_CHECK_INTERVAL_OPTIONS:
                return None

            parsed = parse_target_and_page(payload=target_and_page)

            if parsed is None:
                return None

            target_id, page = parsed
            return "set", target_id, page, interval_minutes

        return None
