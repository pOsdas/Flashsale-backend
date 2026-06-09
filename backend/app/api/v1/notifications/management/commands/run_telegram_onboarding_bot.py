import json
import time
import signal

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand

from app.api.v1.common.rate_limit import check_rate_limit
from app.api.v1.notifications.services.telegram_onboarding import (
    TelegramOnboardingError,
    TelegramOnboardingService,
)
from app.core.logging import get_logger


logger = get_logger(__name__)


MESSAGE_OPEN_CONNECT_LINK = (
    "Чтобы подключить Telegram-уведомления, откройте ссылку "
    "подключения в личном кабинете Flashsale Signals."
)

MESSAGE_START_WITHOUT_TOKEN = (
    "Сначала откройте ссылку подключения в личном кабинете "
    "Flashsale Signals."
)

MESSAGE_CONNECT_SUCCESS = (
    "✅ Telegram успешно подключен.\n\n"
    "Теперь вы будете получать уведомления Flashsale Signals "
    "об изменениях товаров."
)

MESSAGE_CONNECT_ERROR_SUFFIX = (
    "Создайте новую ссылку подключения в личном кабинете "
    "Flashsale Signals и попробуйте еще раз."
)


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

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.should_stop = False

    def handle(self, *args, **options) -> None:
        if not settings.NOTIF_TELEGRAM_BOT_TOKEN:
            raise RuntimeError("NOTIF_TELEGRAM_BOT_TOKEN is empty")

        self._register_signal_handlers()

        reply_rate_limit_limit = settings.NOTIF_TELEGRAM_REPLY_RATE_LIMIT_LIMIT
        reply_rate_limit_window_seconds = settings.NOTIF_TELEGRAM_REPLY_RATE_LIMIT_WINDOW_SECONDS
        drop_pending_updates_on_start = settings.NOTIF_TELEGRAM_DROP_PENDING_UPDATES_ON_START

        bot = TelegramBotClient(
            token=settings.NOTIF_TELEGRAM_BOT_TOKEN,
        )

        offset = None

        logger.info(
            "Telegram onboarding bot started",
            extra={
                "service": "telegram_onboarding_bot",
                "reply_rate_limit_limit": reply_rate_limit_limit,
                "reply_rate_limit_window_seconds": reply_rate_limit_window_seconds,
                "drop_pending_updates_on_start": drop_pending_updates_on_start,
            },
        )

        try:
            if drop_pending_updates_on_start:
                bot.drop_pending_updates()

                logger.info(
                    "Telegram pending updates dropped",
                    extra={
                        "service": "telegram_onboarding_bot",
                    },
                )

            while not self.should_stop:
                try:
                    updates = bot.get_updates(offset=offset)

                    for update in updates:
                        if self.should_stop:
                            break

                        offset = update["update_id"] + 1

                        self._handle_update(
                            bot=bot,
                            update=update,
                            reply_rate_limit_limit=reply_rate_limit_limit,
                            reply_rate_limit_window_seconds=reply_rate_limit_window_seconds,
                        )

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

            logger.info(
                "Telegram onboarding bot stopped",
                extra={
                    "service": "telegram_onboarding_bot",
                },
            )

    def _register_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, self._handle_stop_signal)
        signal.signal(signal.SIGTERM, self._handle_stop_signal)

    def _handle_stop_signal(self, signum, frame) -> None:
        self.should_stop = True

        logger.info(
            "Telegram onboarding bot stopping",
            extra={
                "service": "telegram_onboarding_bot",
                "signal": signum,
            },
        )

    def _handle_update(
        self,
        bot: TelegramBotClient,
        update: dict,
        reply_rate_limit_limit: int,
        reply_rate_limit_window_seconds: int,
    ) -> None:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        text = message.get("text") or ""

        chat_id = str(chat.get("id") or "")

        if not chat_id:
            return

        if not text.startswith("/start"):
            self._send_rate_limited_message(
                bot=bot,
                chat_id=chat_id,
                text=MESSAGE_OPEN_CONNECT_LINK,
                limit=reply_rate_limit_limit,
                window_seconds=reply_rate_limit_window_seconds,
            )
            return

        parts = text.split(maxsplit=1)

        if len(parts) != 2:
            self._send_rate_limited_message(
                bot=bot,
                chat_id=chat_id,
                text=MESSAGE_START_WITHOUT_TOKEN,
                limit=reply_rate_limit_limit,
                window_seconds=reply_rate_limit_window_seconds,
            )
            return

        token = parts[1].strip()

        try:
            channel = TelegramOnboardingService.connect_chat(
                token=token,
                telegram_chat_id=chat_id,
            )

        except TelegramOnboardingError as exc:
            self._send_rate_limited_message(
                bot=bot,
                chat_id=chat_id,
                text=f"{exc}\n\n{MESSAGE_CONNECT_ERROR_SUFFIX}",
                limit=reply_rate_limit_limit,
                window_seconds=reply_rate_limit_window_seconds,
            )
            return

        logger.info(
            "Telegram chat connected successfully",
            extra={
                "service": "telegram_onboarding_bot",
                "user_id": str(channel.user_id),
                "channel_id": str(channel.id),
                "chat_id": chat_id,
            },
        )

        self._send_rate_limited_message(
            bot=bot,
            chat_id=chat_id,
            text=MESSAGE_CONNECT_SUCCESS,
            limit=reply_rate_limit_limit,
            window_seconds=reply_rate_limit_window_seconds,
        )

    def _send_rate_limited_message(
        self,
        bot: TelegramBotClient,
        chat_id: str,
        text: str,
        limit: int,
        window_seconds: int,
    ) -> None:
        rate_limit_key = f"telegram_onboarding_bot:reply:{chat_id}"

        result = check_rate_limit(
            key=rate_limit_key,
            limit=limit,
            window_seconds=window_seconds,
        )

        if not result.allowed:
            logger.warning(
                "Telegram onboarding reply skipped by Redis rate limit",
                extra={
                    "service": "telegram_onboarding_bot",
                    "chat_id": chat_id,
                    "limit": result.limit,
                    "remaining": result.remaining,
                    "retry_after_seconds": result.retry_after_seconds,
                },
            )
            return

        bot.send_message(
            chat_id=chat_id,
            text=text,
        )
