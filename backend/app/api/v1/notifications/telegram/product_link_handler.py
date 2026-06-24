from app.api.v1.common.rate_limit import check_rate_limit
from app.api.v1.monitoring.services.marketplace_url import (
    MarketplaceUrlError,
    resolve_marketplace_url,
)
from app.api.v1.monitoring.services.product_preview import (
    ProductPreviewError,
    ProductPreviewService,
)
from app.api.v1.notifications.telegram.keyboards import (
    build_product_preview_keyboard,
)
from app.api.v1.notifications.telegram.pending_product import (
    PendingProductStoreError,
    TelegramPendingProductStore,
)
from app.api.v1.notifications.telegram.product_presenter import (
    build_product_preview_text,
)
from app.api.v1.notifications.telegram.replies import TelegramReplyService
from app.api.v1.notifications.telegram.user_context import (
    TelegramUserContext,
)
from app.core.logging import get_logger


logger = get_logger(__name__)


class TelegramProductLinkHandler:
    def __init__(
        self,
        *,
        replies: TelegramReplyService,
        preview_service: ProductPreviewService,
        pending_store: TelegramPendingProductStore,
        preview_rate_limit: int = 5,
        preview_rate_limit_window_seconds: int = 60,
    ) -> None:
        self.replies = replies
        self.preview_service = preview_service
        self.pending_store = pending_store
        self.preview_rate_limit = preview_rate_limit
        self.preview_rate_limit_window_seconds = (
            preview_rate_limit_window_seconds
        )

    def handle(
        self,
        *,
        user_context: TelegramUserContext,
        text: str,
    ) -> None:
        try:
            resolved_url = resolve_marketplace_url(
                text=text,
            )
        except MarketplaceUrlError as exc:
            self.replies.send_message(
                chat_id=user_context.telegram_chat_id,
                text=str(exc),
            )
            return

        if not self._check_preview_rate_limit(
            user_context=user_context,
        ):
            return

        try:
            preview = self.preview_service.preview_product(
                marketplace=resolved_url.marketplace,
                url=resolved_url.url,
            )
        except ProductPreviewError as exc:
            self.replies.send_message(
                chat_id=user_context.telegram_chat_id,
                text=f"⚠️ {exc}",
            )
            return

        try:
            pending_product = self.pending_store.create(
                user_id=user_context.user.pk,
                telegram_chat_id=(
                    user_context.telegram_chat_id
                ),
                marketplace=resolved_url.marketplace,
                url=resolved_url.url,
                external_id=preview.external_id,
                title=preview.title,
                seller_name=preview.seller_name,
                brand=preview.brand,
                price=preview.price,
                old_price=preview.old_price,
                currency=preview.currency,
                is_available=preview.is_available,
                rating=preview.rating,
                reviews_count=preview.reviews_count,
            )
        except PendingProductStoreError as exc:
            logger.exception(
                "Failed to store Telegram pending product",
                extra={
                    "service": "telegram_bot",
                    "user_id": str(user_context.user.pk),
                    "chat_id": user_context.telegram_chat_id,
                    "marketplace": resolved_url.marketplace,
                },
            )
            self.replies.send_message(
                chat_id=user_context.telegram_chat_id,
                text=f"⚠️ {exc}",
            )
            return

        sent = self.replies.send_message(
            chat_id=user_context.telegram_chat_id,
            text=build_product_preview_text(
                marketplace=resolved_url.marketplace,
                preview=preview,
            ),
            reply_markup=build_product_preview_keyboard(
                token=pending_product.token,
            ),
        )

        if not sent:
            self.pending_store.delete(
                token=pending_product.token,
            )

    def _check_preview_rate_limit(
        self,
        *,
        user_context: TelegramUserContext,
    ) -> bool:
        result = check_rate_limit(
            key=(
                "telegram_bot:preview:"
                f"{user_context.user.pk}"
            ),
            limit=self.preview_rate_limit,
            window_seconds=(
                self.preview_rate_limit_window_seconds
            ),
        )

        if result.allowed:
            return True

        retry_after_seconds = max(
            int(result.retry_after_seconds),
            1,
        )
        self.replies.send_message(
            chat_id=user_context.telegram_chat_id,
            text=(
                "Слишком много запросов на проверку товара. "
                f"Повторите через {retry_after_seconds} секунд."
            ),
        )
        return False
