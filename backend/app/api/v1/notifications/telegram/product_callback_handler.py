from typing import Any

from app.api.v1.monitoring.models import MonitoringTargetRole
from app.api.v1.monitoring.services.target_duplicate_service import (
    find_existing_monitoring_target,
)
from app.api.v1.monitoring.services.target_service import (
    MonitoringTargetServiceError,
    create_monitoring_target,
)
from app.api.v1.notifications.telegram.client import TelegramBotClient
from app.api.v1.notifications.telegram.keyboards import (
    PRODUCT_ADD_CALLBACK_PREFIX,
    PRODUCT_CANCEL_CALLBACK_PREFIX,
    build_empty_inline_keyboard,
    build_existing_product_keyboard,
    build_product_preview_keyboard,
)
from app.api.v1.notifications.telegram.pending_product import (
    PendingTelegramProduct,
    TelegramPendingProductStore,
)
from app.api.v1.notifications.telegram.product_presenter import (
    build_product_added_text,
    build_product_already_tracked_text,
    build_product_cancelled_text,
    build_product_retry_text,
)
from app.api.v1.notifications.telegram.user_context import (
    TelegramUserContext,
    TelegramUserContextResolver,
)
from app.core.logging import get_logger


logger = get_logger(__name__)


MESSAGE_CALLBACK_EXPIRED = (
    "Это подтверждение уже использовано или устарело. "
    "Отправьте ссылку на товар ещё раз."
)
MESSAGE_CALLBACK_BUSY = (
    "Этот товар уже добавляется. Подождите несколько секунд."
)
MESSAGE_CALLBACK_FORBIDDEN = (
    "Это действие относится к другому пользователю."
)
MESSAGE_CONNECT_REQUIRED = (
    "Telegram не подключён к аккаунту. "
    "Откройте персональную ссылку подключения."
)


class TelegramProductCallbackHandler:
    def __init__(
        self,
        *,
        client: TelegramBotClient,
        pending_store: TelegramPendingProductStore,
        user_context_resolver: TelegramUserContextResolver,
    ) -> None:
        self.client = client
        self.pending_store = pending_store
        self.user_context_resolver = user_context_resolver

    def can_handle(self, *, callback_data: str) -> bool:
        return callback_data.startswith(
            PRODUCT_ADD_CALLBACK_PREFIX
        ) or callback_data.startswith(
            PRODUCT_CANCEL_CALLBACK_PREFIX
        )

    def handle(
        self,
        *,
        callback_query: dict[str, Any],
    ) -> None:
        callback_query_id = str(
            callback_query.get("id") or ""
        ).strip()
        callback_data = str(
            callback_query.get("data") or ""
        ).strip()
        message = callback_query.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id") or "").strip()
        message_id = message.get("message_id")
        from_user = callback_query.get("from") or {}
        from_user_id = str(from_user.get("id") or "").strip()

        if not callback_query_id:
            return

        if not chat_id or not isinstance(message_id, int):
            self.client.answer_callback_query(
                callback_query_id=callback_query_id,
                text=MESSAGE_CALLBACK_EXPIRED,
                show_alert=True,
            )
            return

        if from_user_id and from_user_id != chat_id:
            self.client.answer_callback_query(
                callback_query_id=callback_query_id,
                text=MESSAGE_CALLBACK_FORBIDDEN,
                show_alert=True,
            )
            return

        user_context = self.user_context_resolver.resolve(
            telegram_chat_id=chat_id,
        )

        if user_context is None:
            self.client.answer_callback_query(
                callback_query_id=callback_query_id,
                text=MESSAGE_CONNECT_REQUIRED,
                show_alert=True,
            )
            return

        action, token = self._parse_callback_data(
            callback_data=callback_data,
        )
        pending_product = self.pending_store.get(
            token=token,
        )

        if pending_product is None:
            self.client.answer_callback_query(
                callback_query_id=callback_query_id,
                text=MESSAGE_CALLBACK_EXPIRED,
                show_alert=True,
            )
            return

        if not self._belongs_to_user(
            pending_product=pending_product,
            user_context=user_context,
        ):
            self.client.answer_callback_query(
                callback_query_id=callback_query_id,
                text=MESSAGE_CALLBACK_FORBIDDEN,
                show_alert=True,
            )
            return

        if action == "cancel":
            self._cancel_product(
                callback_query_id=callback_query_id,
                chat_id=chat_id,
                message_id=message_id,
                pending_product=pending_product,
            )
            return

        self._add_product(
            callback_query_id=callback_query_id,
            chat_id=chat_id,
            message_id=message_id,
            user_context=user_context,
            pending_product=pending_product,
        )

    def _add_product(
        self,
        *,
        callback_query_id: str,
        chat_id: str,
        message_id: int,
        user_context: TelegramUserContext,
        pending_product: PendingTelegramProduct,
    ) -> None:
        token = pending_product.token

        if not self.pending_store.acquire_lock(token=token):
            self.client.answer_callback_query(
                callback_query_id=callback_query_id,
                text=MESSAGE_CALLBACK_BUSY,
                show_alert=False,
            )
            return

        self.client.answer_callback_query(
            callback_query_id=callback_query_id,
            text="Добавляю товар...",
            show_alert=False,
        )

        try:
            existing_target = find_existing_monitoring_target(
                user=user_context.user,
                marketplace=pending_product.marketplace,
                external_id=pending_product.external_id,
                url=pending_product.url,
            )

            if existing_target is not None:
                self.pending_store.delete(token=token)
                self.client.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=build_product_already_tracked_text(
                        target=existing_target,
                    ),
                    reply_markup=build_existing_product_keyboard(
                        target_id=str(existing_target.id),
                    ),
                )
                return

            target = create_monitoring_target(
                user=user_context.user,
                validated_data={
                    "marketplace": pending_product.marketplace,
                    "url": pending_product.url,
                    "role": MonitoringTargetRole.COMPETITOR,
                    "check_interval_minutes": 60,
                },
            )

        except MonitoringTargetServiceError as exc:
            logger.warning(
                "Telegram monitoring target creation failed",
                extra={
                    "service": "telegram_bot",
                    "user_id": str(user_context.user.pk),
                    "chat_id": chat_id,
                    "marketplace": pending_product.marketplace,
                    "external_id": pending_product.external_id,
                    "error": str(exc),
                },
            )
            self._show_retry(
                chat_id=chat_id,
                message_id=message_id,
                pending_product=pending_product,
                error_message=str(exc),
            )
            return

        except Exception as exc:
            logger.exception(
                "Unexpected Telegram monitoring target creation error",
                extra={
                    "service": "telegram_bot",
                    "user_id": str(user_context.user.pk),
                    "chat_id": chat_id,
                    "marketplace": pending_product.marketplace,
                    "external_id": pending_product.external_id,
                    "error": str(exc),
                },
            )
            self._show_retry(
                chat_id=chat_id,
                message_id=message_id,
                pending_product=pending_product,
                error_message=(
                    "Внутренняя ошибка. Попробуйте ещё раз."
                ),
            )
            return

        finally:
            self.pending_store.release_lock(token=token)

        self.pending_store.delete(token=token)
        self.client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=build_product_added_text(
                target=target,
                already_existed=False,
            ),
            reply_markup=build_empty_inline_keyboard(),
        )

    def _cancel_product(
        self,
        *,
        callback_query_id: str,
        chat_id: str,
        message_id: int,
        pending_product: PendingTelegramProduct,
    ) -> None:
        self.pending_store.delete(
            token=pending_product.token,
        )
        self.client.answer_callback_query(
            callback_query_id=callback_query_id,
            text="Добавление отменено.",
            show_alert=False,
        )
        self.client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=build_product_cancelled_text(
                pending_product=pending_product,
            ),
            reply_markup=build_empty_inline_keyboard(),
        )

    def _show_retry(
        self,
        *,
        chat_id: str,
        message_id: int,
        pending_product: PendingTelegramProduct,
        error_message: str,
    ) -> None:
        self.client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=build_product_retry_text(
                pending_product=pending_product,
                error_message=error_message,
            ),
            reply_markup=build_product_preview_keyboard(
                token=pending_product.token,
            ),
        )

    @staticmethod
    def _parse_callback_data(
        *,
        callback_data: str,
    ) -> tuple[str, str]:
        if callback_data.startswith(
            PRODUCT_ADD_CALLBACK_PREFIX
        ):
            return (
                "add",
                callback_data[
                    len(PRODUCT_ADD_CALLBACK_PREFIX):
                ],
            )

        return (
            "cancel",
            callback_data[
                len(PRODUCT_CANCEL_CALLBACK_PREFIX):
            ],
        )

    @staticmethod
    def _belongs_to_user(
        *,
        pending_product: PendingTelegramProduct,
        user_context: TelegramUserContext,
    ) -> bool:
        return (
            pending_product.user_id
            == str(user_context.user.pk)
            and pending_product.telegram_chat_id
            == user_context.telegram_chat_id
        )
