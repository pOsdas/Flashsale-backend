from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired

from app.api.v1.notifications.models import NotificationChannel


@dataclass(frozen=True)
class TelegramConnectLink:
    token: str
    url: str
    expires_in_seconds: int


class TelegramOnboardingError(Exception):
    pass


class TelegramOnboardingService:
    @classmethod
    def _get_signing_salt(cls) -> str:
        salt = settings.NOTIF_TELEGRAM_CONNECT_SIGNING_SALT

        if not salt:
            raise TelegramOnboardingError(
                "NOTIF_TELEGRAM_CONNECT_SIGNING_SALT is empty"
            )

        return salt

    @classmethod
    def build_connect_link(cls, user) -> TelegramConnectLink:
        if not settings.NOTIF_TELEGRAM_BOT_USERNAME:
            raise TelegramOnboardingError("NOTIF_TELEGRAM_BOT_USERNAME is empty")

        token = signing.dumps(
            {
                "user_id": user.id,
            },
            salt=cls._get_signing_salt(),
        )

        url = f"https://t.me/{settings.NOTIF_TELEGRAM_BOT_USERNAME}?start={token}"

        return TelegramConnectLink(
            token=token,
            url=url,
            expires_in_seconds=settings.NOTIF_TELEGRAM_CONNECT_TOKEN_MAX_AGE_SECONDS,
        )

    @classmethod
    def connect_chat(cls, token: str, telegram_chat_id: str) -> NotificationChannel:
        try:
            payload = signing.loads(
                token,
                salt=cls._get_signing_salt(),
                max_age=settings.NOTIF_TELEGRAM_CONNECT_TOKEN_MAX_AGE_SECONDS,
            )
        except SignatureExpired as exc:
            raise TelegramOnboardingError("Ссылка подключения устарела.") from exc
        except BadSignature as exc:
            raise TelegramOnboardingError("Некорректная ссылка подключения.") from exc

        user_id = payload.get("user_id")

        if not user_id:
            raise TelegramOnboardingError("В токене отсутствует user_id.")

        User = get_user_model()

        user = User.objects.filter(id=user_id).first()

        if user is None:
            raise TelegramOnboardingError("Пользователь не найден.")

        NotificationChannel.objects.filter(
            type=NotificationChannel.ChannelType.TELEGRAM,
            telegram_chat_id=telegram_chat_id,
        ).exclude(
            user=user,
        ).update(
            is_active=False,
        )

        channel, _ = NotificationChannel.objects.update_or_create(
            user=user,
            type=NotificationChannel.ChannelType.TELEGRAM,
            telegram_chat_id=telegram_chat_id,
            defaults={
                "is_active": True,
                "email": "",
                "webhook_url": "",
            },
        )

        return channel
