from django.conf import settings
from django.core.management.base import BaseCommand

from app.api.v1.monitoring.services.product_preview import (
    ProductPreviewService,
)
from app.api.v1.notifications.telegram.client import TelegramBotClient
from app.api.v1.notifications.telegram.commands import (
    TELEGRAM_BOT_COMMANDS,
)
from app.api.v1.notifications.telegram.help_handler import (
    TelegramHelpHandler,
)
from app.api.v1.notifications.telegram.pending_product import (
    TelegramPendingProductStore,
)
from app.api.v1.notifications.telegram.polling import (
    TelegramPollingRunner,
)
from app.api.v1.notifications.telegram.product_callback_handler import (
    TelegramProductCallbackHandler,
)
from app.api.v1.notifications.telegram.product_link_handler import (
    TelegramProductLinkHandler,
)
from app.api.v1.notifications.telegram.products_handler import (
    TelegramProductsHandler,
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
        client.set_my_commands(
            commands=TELEGRAM_BOT_COMMANDS,
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
        pending_store = TelegramPendingProductStore(
            ttl_seconds=int(
                getattr(
                    settings,
                    "NOTIF_TELEGRAM_PENDING_PRODUCT_TTL_SECONDS",
                    600,
                )
            ),
            lock_seconds=int(
                getattr(
                    settings,
                    "NOTIF_TELEGRAM_PENDING_PRODUCT_LOCK_SECONDS",
                    30,
                )
            ),
        )
        start_handler = TelegramStartHandler(
            replies=replies,
            user_context_resolver=user_context_resolver,
        )
        help_handler = TelegramHelpHandler(
            replies=replies,
        )
        product_link_handler = TelegramProductLinkHandler(
            replies=replies,
            preview_service=ProductPreviewService(),
            pending_store=pending_store,
            preview_rate_limit=int(
                getattr(
                    settings,
                    "NOTIF_TELEGRAM_PREVIEW_RATE_LIMIT_LIMIT",
                    5,
                )
            ),
            preview_rate_limit_window_seconds=int(
                getattr(
                    settings,
                    "NOTIF_TELEGRAM_PREVIEW_RATE_LIMIT_WINDOW_SECONDS",
                    60,
                )
            ),
        )
        product_callback_handler = (
            TelegramProductCallbackHandler(
                client=client,
                pending_store=pending_store,
                user_context_resolver=(
                    user_context_resolver
                ),
            )
        )
        products_handler = TelegramProductsHandler(
            client=client,
            replies=replies,
            user_context_resolver=user_context_resolver,
            page_size=int(
                getattr(
                    settings,
                    "NOTIF_TELEGRAM_PRODUCTS_PAGE_SIZE",
                    3,
                )
            ),
        )
        router = TelegramUpdateRouter(
            client=client,
            replies=replies,
            start_handler=start_handler,
            help_handler=help_handler,
            user_context_resolver=user_context_resolver,
            product_link_handler=product_link_handler,
            product_callback_handler=(
                product_callback_handler
            ),
            products_handler=products_handler,
        )
        runner = TelegramPollingRunner(
            client=client,
            router=router,
            drop_pending_updates_on_start=(
                settings.NOTIF_TELEGRAM_DROP_PENDING_UPDATES_ON_START
            ),
        )

        runner.run()
