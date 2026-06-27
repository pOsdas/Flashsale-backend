from app.api.v1.notifications.telegram.commands import HELP_MESSAGE
from app.api.v1.notifications.telegram.replies import (
    TelegramReplyService,
)


class TelegramHelpHandler:
    def __init__(
        self,
        *,
        replies: TelegramReplyService,
    ) -> None:
        self.replies = replies

    def handle(
        self,
        *,
        chat_id: str,
    ) -> None:
        self.replies.send_message(
            chat_id=chat_id,
            text=HELP_MESSAGE,
        )
