import json
import time

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand

from app.api.v1.notifications.services.telegram_onboarding import (
    TelegramOnboardingError,
    TelegramOnboardingService,
)
from app.core.logging import get_logger


logger = get_logger(__name__)


class TelegramBotClient:
    def __init__(self, token: str, timeout_seconds: int = 30) -> None:
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.base_url = f"https://api.telegram.org/bot{token}"

        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(
                timeout_seconds + 5,
                connect=10,
                read=timeout_seconds + 5,
                write=10,
                pool=10,
            ),
        )

    def drop_pending_updates(self) -> None:
        response = self.client.post(
            "/deleteWebhook",
            json={
                "drop_pending_updates": True,
            },
        )
        response.raise_for_status()

        data = response.json()

        if not data.get("ok"):
            raise RuntimeError(f"Telegram deleteWebhook failed: {data}")

    def get_updates(self, offset: int | None = None) -> list[dict]:
        params = {
            "timeout": self.timeout_seconds,
            "allowed_updates": json.dumps(["message"]),
        }

        if offset is not None:
            params["offset"] = offset

        response = self.client.get(
            "/getUpdates",
            params=params,
        )
        response.raise_for_status()

        data = response.json()

        if not data.get("ok"):
            raise RuntimeError(f"Telegram getUpdates failed: {data}")

        return data.get("result", [])

    def send_message(self, chat_id: str, text: str) -> None:
        response = self.client.post(
            "/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
        )
        response.raise_for_status()

        data = response.json()

        if not data.get("ok"):
            raise RuntimeError(f"Telegram sendMessage failed: {data}")

    def close(self) -> None:
        self.client.close()


class Command(BaseCommand):
    help = "Run Telegram onboarding bot polling"

    def handle(self, *args, **options) -> None:
        if not settings.NOTIF_TELEGRAM_BOT_TOKEN:
            raise RuntimeError("NOTIF_TELEGRAM_BOT_TOKEN is empty")

        bot = TelegramBotClient(
            token=settings.NOTIF_TELEGRAM_BOT_TOKEN,
        )

        offset = None

        logger.info(
            "Telegram onboarding bot started",
            extra={
                "service": "telegram_onboarding_bot",
            },
        )

        try:
            bot.drop_pending_updates()

            logger.info(
                "Telegram pending updates dropped",
                extra={
                    "service": "telegram_onboarding_bot",
                },
            )

            while True:
                try:
                    updates = bot.get_updates(offset=offset)

                    for update in updates:
                        offset = update["update_id"] + 1
                        self._handle_update(bot=bot, update=update)

                except httpx.HTTPError as exc:
                    logger.exception(
                        "Telegram onboarding bot HTTP error",
                        extra={
                            "service": "telegram_onboarding_bot",
                            "error": str(exc),
                        },
                    )
                    time.sleep(5)

                except Exception as exc:
                    logger.exception(
                        "Telegram onboarding bot error",
                        extra={
                            "service": "telegram_onboarding_bot",
                            "error": str(exc),
                        },
                    )
                    time.sleep(5)

        finally:
            bot.close()

    def _handle_update(self, bot: TelegramBotClient, update: dict) -> None:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        text = (message.get("text") or "").strip()

        chat_id = str(chat.get("id") or "")

        if not chat_id:
            return

        if not text.startswith("/start"):
            logger.info(
                "Telegram onboarding bot ignored non-start message",
                extra={
                    "service": "telegram_onboarding_bot",
                    "chat_id": chat_id,
                },
            )
            return

        parts = text.split(maxsplit=1)

        if len(parts) != 2:
            bot.send_message(
                chat_id=chat_id,
                text=(
                    "Сначала откройте ссылку подключения в личном кабинете "
                    "Flashsale Signals."
                ),
            )
            return

        token = parts[1].strip()

        try:
            TelegramOnboardingService.connect_chat(
                token=token,
                telegram_chat_id=chat_id,
            )

        except TelegramOnboardingError as exc:
            bot.send_message(
                chat_id=chat_id,
                text=(
                    f"{exc}\n\n"
                    "Создайте новую ссылку подключения в личном кабинете "
                    "Flashsale Signals и попробуйте еще раз."
                ),
            )
            return

        bot.send_message(
            chat_id=chat_id,
            text=(
                "✅ Telegram успешно подключен.\n\n"
                "Теперь вы будете получать уведомления Flashsale Signals "
                "об изменениях товаров."
            ),
        )
