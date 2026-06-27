from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TelegramTargetCallbackEnvelope:
    callback_query_id: str
    callback_data: str
    chat_id: str
    message_id: int
    from_user_id: str

    @property
    def belongs_to_chat_user(self) -> bool:
        return (
            not self.from_user_id
            or self.from_user_id == self.chat_id
        )


def extract_target_callback_envelope(
    *,
    callback_query: dict[str, Any],
) -> TelegramTargetCallbackEnvelope | None:
    callback_query_id = str(
        callback_query.get("id") or ""
    ).strip()
    callback_data = str(
        callback_query.get("data") or ""
    ).strip()
    message = callback_query.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "").strip()
    message_id = message.get("message_id")
    from_user = callback_query.get("from") or {}
    from_user_id = str(from_user.get("id") or "").strip()

    if (
        not callback_query_id
        or not chat_id
        or not isinstance(message_id, int)
    ):
        return None

    return TelegramTargetCallbackEnvelope(
        callback_query_id=callback_query_id,
        callback_data=callback_data,
        chat_id=chat_id,
        message_id=message_id,
        from_user_id=from_user_id,
    )


def parse_target_and_page(
    *,
    payload: str,
) -> tuple[UUID, int] | None:
    try:
        target_id_raw, page_raw = payload.rsplit(":", maxsplit=1)
        target_id = UUID(target_id_raw)
        page = max(1, int(page_raw))
    except (TypeError, ValueError):
        return None

    return target_id, page
