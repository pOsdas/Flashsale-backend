from app.api.v1.notifications.services.telegram_onboarding import (
    TelegramOnboardingError,
    TelegramOnboardingService,
)
from app.api.v1.notifications.telegram.replies import (
    TelegramReplyService,
)
from app.api.v1.notifications.telegram.user_context import (
    TelegramUserContextResolver,
)
from app.core.logging import get_logger


logger = get_logger(__name__)


MESSAGE_START_WITHOUT_TOKEN = (
    "Сначала откройте персональную ссылку подключения "
    "в личном кабинете Flashsale Signals."
)

MESSAGE_ALREADY_CONNECTED = (
    "✅ Telegram уже подключён к Flashsale Signals.\n\n"
    "Отправьте ссылку на товар Wildberries или Ozon, "
    "чтобы добавить его в отслеживание.\n\n"
    "Используйте /products для управления товарами."
)

MESSAGE_CONNECT_SUCCESS = (
    "✅ Telegram успешно подключён.\n\n"
    "Отправьте ссылку на товар Wildberries или Ozon, "
    "чтобы добавить его в отслеживание.\n\n"
    "Используйте /products для управления товарами."
)

MESSAGE_CONNECT_ERROR_SUFFIX = (
    "Создайте новую ссылку подключения в личном кабинете "
    "Flashsale Signals и попробуйте ещё раз."
)


class TelegramStartHandler:
    def __init__(
        self,
        *,
        replies: TelegramReplyService,
        user_context_resolver: TelegramUserContextResolver,
    ) -> None:
        self.replies = replies
        self.user_context_resolver = user_context_resolver

    def handle(
        self,
        *,
        chat_id: str,
        token: str | None,
    ) -> None:
        normalized_token = (token or "").strip()

        if not normalized_token:
            self._handle_without_token(
                chat_id=chat_id,
            )
            return

        try:
            channel = TelegramOnboardingService.connect_chat(
                token=normalized_token,
                telegram_chat_id=chat_id,
            )

        except TelegramOnboardingError as exc:
            self.replies.send_message(
                chat_id=chat_id,
                text=(
                    f"{exc}\n\n"
                    f"{MESSAGE_CONNECT_ERROR_SUFFIX}"
                ),
            )
            return

        logger.info(
            "Telegram chat connected successfully",
            extra={
                "service": "telegram_bot",
                "user_id": str(channel.user_id),
                "channel_id": str(channel.id),
                "chat_id": chat_id,
            },
        )

        self.replies.send_message(
            chat_id=chat_id,
            text=MESSAGE_CONNECT_SUCCESS,
        )

    def _handle_without_token(
        self,
        *,
        chat_id: str,
    ) -> None:
        user_context = self.user_context_resolver.resolve(
            telegram_chat_id=chat_id,
        )

        if user_context is None:
            message = MESSAGE_START_WITHOUT_TOKEN
        else:
            message = MESSAGE_ALREADY_CONNECTED

        self.replies.send_message(
            chat_id=chat_id,
            text=message,
        )
