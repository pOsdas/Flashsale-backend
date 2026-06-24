from collections.abc import Mapping
from typing import Any

from app.api.v1.common.rate_limit import check_rate_limit
from app.api.v1.notifications.telegram.client import TelegramBotClient
from app.core.logging import get_logger


logger = get_logger(__name__)


class TelegramReplyService:
    def __init__(
        self,
        *,
        client: TelegramBotClient,
        rate_limit_limit: int,
        rate_limit_window_seconds: int,
    ) -> None:
        self.client = client
        self.rate_limit_limit = rate_limit_limit
        self.rate_limit_window_seconds = (
            rate_limit_window_seconds
        )

    def send_message(
        self,
        *,
        chat_id: int | str,
        text: str,
        reply_markup: Mapping[str, Any] | None = None,
    ) -> bool:
        normalized_chat_id = str(chat_id).strip()
        rate_limit_key = (
            f"telegram_bot:reply:{normalized_chat_id}"
        )

        result = check_rate_limit(
            key=rate_limit_key,
            limit=self.rate_limit_limit,
            window_seconds=self.rate_limit_window_seconds,
        )

        if not result.allowed:
            logger.warning(
                "Telegram bot reply skipped by Redis rate limit",
                extra={
                    "service": "telegram_bot",
                    "chat_id": normalized_chat_id,
                    "limit": result.limit,
                    "remaining": result.remaining,
                    "retry_after_seconds": (
                        result.retry_after_seconds
                    ),
                },
            )
            return False

        self.client.send_message(
            chat_id=normalized_chat_id,
            text=text,
            reply_markup=reply_markup,
        )
        return True
