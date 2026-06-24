from django.conf import settings
from django.core.management.base import BaseCommand

from app.api.v1.notifications.telegram.client import TelegramBotClient
from app.api.v1.notifications.telegram.polling import (
    TelegramPollingRunner,
)
from app.api.v1.notifications.telegram.replies import (
    TelegramReplyService,
)
from app.api.v1.notifications.telegram.router import TelegramUpdateRouter
from app.api.v1.notifications.telegram.start_handler import (
    TelegramStartHandler,
)
from app.api.v1.notifications.telegram.user_context import (
    TelegramUserContextResolver,
)


class Command(BaseCommand):
    help = "Run Telegram bot polling"

    def handle(self, *args, **options) -> None:
        bot_token = settings.NOTIF_TELEGRAM_BOT_TOKEN

        if not bot_token:
            raise RuntimeError(
                "NOTIF_TELEGRAM_BOT_TOKEN is empty"
            )

        client = TelegramBotClient(
            token=bot_token,
        )
        user_context_resolver = TelegramUserContextResolver()
        replies = TelegramReplyService(
            client=client,
            rate_limit_limit=(
                settings.NOTIF_TELEGRAM_REPLY_RATE_LIMIT_LIMIT
            ),
            rate_limit_window_seconds=(
                settings.NOTIF_TELEGRAM_REPLY_RATE_LIMIT_WINDOW_SECONDS
            ),
        )
        start_handler = TelegramStartHandler(
            replies=replies,
            user_context_resolver=user_context_resolver,
        )
        router = TelegramUpdateRouter(
            client=client,
            replies=replies,
            start_handler=start_handler,
            user_context_resolver=user_context_resolver,
        )
        runner = TelegramPollingRunner(
            client=client,
            router=router,
            drop_pending_updates_on_start=(
                settings.NOTIF_TELEGRAM_DROP_PENDING_UPDATES_ON_START
            ),
        )

        runner.run()
