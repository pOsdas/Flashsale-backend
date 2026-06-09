import time

import httpx
from django.conf import settings

from app.api.v1.notifications.notification_metrics import (
    TELEGRAM_NOTIFICATION_DURATION_SECONDS,
    TELEGRAM_NOTIFICATIONS_TOTAL,
)
from app.core.logging import get_logger


logger = get_logger(__name__)


class TelegramDeliveryError(Exception):
    pass


class TelegramDeliveryAdapter:
    TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(
        self,
        bot_token: str | None = None,
        timeout_seconds: int = 10,
    ) -> None:
        self.bot_token = bot_token or settings.NOTIF_TELEGRAM_BOT_TOKEN
        self.timeout_seconds = timeout_seconds

    def send_message(self, chat_id: int | str, text: str) -> None:
        started_at = time.monotonic()

        try:
            self._send_message(chat_id=chat_id, text=text)
        except Exception:
            TELEGRAM_NOTIFICATIONS_TOTAL.labels(status="failed").inc()
            raise
        else:
            TELEGRAM_NOTIFICATIONS_TOTAL.labels(status="sent").inc()
        finally:
            duration = time.monotonic() - started_at
            TELEGRAM_NOTIFICATION_DURATION_SECONDS.observe(duration)

    def _send_message(self, chat_id: int | str, text: str) -> None:
        if not self.bot_token:
            raise TelegramDeliveryError("NOTIF_TELEGRAM_BOT_TOKEN is empty")

        normalized_chat_id = self._normalize_chat_id(chat_id)

        if not text:
            raise TelegramDeliveryError("Telegram message text is empty")

        url = self.TELEGRAM_API_URL.format(token=self.bot_token)

        payload = {
            "chat_id": normalized_chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }

        logger.info(
            "Sending Telegram message",
            extra={
                "service": "telegram_delivery",
                "chat_id": str(normalized_chat_id),
                "text_length": len(text),
            },
        )

        try:
            response = httpx.post(
                url=url,
                json=payload,
                timeout=self.timeout_seconds,
            )

        except httpx.TimeoutException as exc:
            logger.exception(
                "Telegram request timeout",
                extra={
                    "service": "telegram_delivery",
                    "chat_id": str(normalized_chat_id),
                    "timeout_seconds": self.timeout_seconds,
                },
            )

            raise TelegramDeliveryError("Telegram request timeout") from exc

        except httpx.RequestError as exc:
            logger.exception(
                "Telegram request error",
                extra={
                    "service": "telegram_delivery",
                    "chat_id": str(normalized_chat_id),
                    "error": str(exc),
                },
            )

            raise TelegramDeliveryError(f"Telegram request error: {exc}") from exc

        response_text = response.text

        try:
            response_data = response.json()
        except ValueError as exc:
            logger.exception(
                "Telegram returned invalid JSON",
                extra={
                    "service": "telegram_delivery",
                    "chat_id": str(normalized_chat_id),
                    "status_code": response.status_code,
                    "response_text": response_text,
                },
            )

            raise TelegramDeliveryError(
                f"Telegram returned invalid JSON: {response_text}"
            ) from exc

        if response.status_code >= 400:
            logger.error(
                "Telegram HTTP error",
                extra={
                    "service": "telegram_delivery",
                    "chat_id": str(normalized_chat_id),
                    "status_code": response.status_code,
                    "response": response_data,
                },
            )

            raise TelegramDeliveryError(
                f"Telegram HTTP error {response.status_code}: {response_text}"
            )

        if not response_data.get("ok"):
            logger.error(
                "Telegram returned error response",
                extra={
                    "service": "telegram_delivery",
                    "chat_id": str(normalized_chat_id),
                    "status_code": response.status_code,
                    "response": response_data,
                },
            )

            raise TelegramDeliveryError(
                f"Telegram returned error response: {response_data}"
            )

        logger.info(
            "Telegram message sent successfully",
            extra={
                "service": "telegram_delivery",
                "chat_id": str(normalized_chat_id),
                "status_code": response.status_code,
            },
        )

    def _normalize_chat_id(self, chat_id: int | str) -> int | str:
        if chat_id is None:
            raise TelegramDeliveryError("Telegram chat_id is empty")

        if isinstance(chat_id, int):
            return chat_id

        cleaned_chat_id = str(chat_id).strip()

        if not cleaned_chat_id:
            raise TelegramDeliveryError("Telegram chat_id is empty")

        if cleaned_chat_id.lstrip("-").isdigit():
            return int(cleaned_chat_id)

        return cleaned_chat_id
