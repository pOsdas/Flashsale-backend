from typing import Any

from app.api.v1.notifications.telegram.client import TelegramBotClient
from app.api.v1.notifications.telegram.product_callback_handler import (
    TelegramProductCallbackHandler,
)
from app.api.v1.notifications.telegram.product_link_handler import (
    TelegramProductLinkHandler,
)
from app.api.v1.notifications.telegram.replies import (
    TelegramReplyService,
)
from app.api.v1.notifications.telegram.start_handler import (
    TelegramStartHandler,
)
from app.api.v1.notifications.telegram.user_context import (
    TelegramUserContextResolver,
)
from app.core.logging import get_logger


logger = get_logger(__name__)


MESSAGE_PRIVATE_CHAT_ONLY = (
    "Управление Flashsale Signals доступно только "
    "в личном чате с ботом."
)

MESSAGE_OPEN_CONNECT_LINK = (
    "Telegram ещё не подключён к вашему аккаунту.\n\n"
    "Откройте персональную ссылку подключения "
    "в личном кабинете Flashsale Signals."
)

MESSAGE_PRODUCTS_NOT_AVAILABLE = (
    "Команда /products будет добавлена следующим этапом.\n\n"
    "Сейчас отправьте ссылку на товар Wildberries или Ozon, "
    "чтобы добавить его в отслеживание."
)

MESSAGE_UNKNOWN_COMMAND = (
    "Неизвестная команда.\n\n"
    "Отправьте ссылку на товар Wildberries или Ozon."
)

MESSAGE_CALLBACK_NOT_AVAILABLE = (
    "Это действие пока недоступно."
)


class TelegramUpdateRouter:
    def __init__(
        self,
        *,
        client: TelegramBotClient,
        replies: TelegramReplyService,
        start_handler: TelegramStartHandler,
        user_context_resolver: TelegramUserContextResolver,
        product_link_handler: TelegramProductLinkHandler,
        product_callback_handler: TelegramProductCallbackHandler,
    ) -> None:
        self.client = client
        self.replies = replies
        self.start_handler = start_handler
        self.user_context_resolver = user_context_resolver
        self.product_link_handler = product_link_handler
        self.product_callback_handler = product_callback_handler

    def handle_update(
        self,
        *,
        update: dict[str, Any],
    ) -> None:
        if update.get("callback_query"):
            self._handle_callback_query(
                callback_query=update["callback_query"],
            )
            return

        if update.get("message"):
            self._handle_message(
                message=update["message"],
            )
            return

        logger.debug(
            "Telegram update ignored",
            extra={
                "service": "telegram_bot",
                "update_id": update.get("update_id"),
            },
        )

    def _handle_message(
        self,
        *,
        message: dict[str, Any],
    ) -> None:
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id") or "").strip()
        chat_type = str(chat.get("type") or "").strip()
        text = str(message.get("text") or "").strip()

        if not chat_id:
            return

        if chat_type != "private":
            self.replies.send_message(
                chat_id=chat_id,
                text=MESSAGE_PRIVATE_CHAT_ONLY,
            )
            return

        command, argument = self._parse_command(text=text)

        if command == "/start":
            self.start_handler.handle(
                chat_id=chat_id,
                token=argument,
            )
            return

        user_context = self.user_context_resolver.resolve(
            telegram_chat_id=chat_id,
        )

        if user_context is None:
            self.replies.send_message(
                chat_id=chat_id,
                text=MESSAGE_OPEN_CONNECT_LINK,
            )
            return

        if command == "/products":
            self.replies.send_message(
                chat_id=chat_id,
                text=MESSAGE_PRODUCTS_NOT_AVAILABLE,
            )
            return

        if command is not None:
            self.replies.send_message(
                chat_id=chat_id,
                text=MESSAGE_UNKNOWN_COMMAND,
            )
            return

        self.product_link_handler.handle(
            user_context=user_context,
            text=text,
        )

    def _handle_callback_query(
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
        chat_type = str(chat.get("type") or "").strip()

        if not callback_query_id:
            return

        if chat_type and chat_type != "private":
            self.client.answer_callback_query(
                callback_query_id=callback_query_id,
                text=MESSAGE_PRIVATE_CHAT_ONLY,
                show_alert=True,
            )
            return

        if self.product_callback_handler.can_handle(
            callback_data=callback_data,
        ):
            self.product_callback_handler.handle(
                callback_query=callback_query,
            )
            return

        self.client.answer_callback_query(
            callback_query_id=callback_query_id,
            text=MESSAGE_CALLBACK_NOT_AVAILABLE,
            show_alert=False,
        )

    def _parse_command(
        self,
        *,
        text: str,
    ) -> tuple[str | None, str | None]:
        if not text.startswith("/"):
            return None, None

        parts = text.split(maxsplit=1)
        command = parts[0].split("@", maxsplit=1)[0].lower()
        argument = parts[1].strip() if len(parts) == 2 else None

        return command, argument
