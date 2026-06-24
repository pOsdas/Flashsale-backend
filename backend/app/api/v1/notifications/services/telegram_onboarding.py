import base64
import hmac
import time
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.crypto import salted_hmac

from app.api.v1.notifications.models import NotificationChannel


TELEGRAM_START_TOKEN_SIGNATURE_BYTES = 16
TELEGRAM_START_TOKEN_SIGNATURE_LENGTH = 22
TELEGRAM_START_TOKEN_MAX_LENGTH = 64


@dataclass(frozen=True, slots=True)
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
    def _get_token_max_age_seconds(cls) -> int:
        max_age = int(
            settings.NOTIF_TELEGRAM_CONNECT_TOKEN_MAX_AGE_SECONDS
        )

        if max_age <= 0:
            raise TelegramOnboardingError(
                "NOTIF_TELEGRAM_CONNECT_TOKEN_MAX_AGE_SECONDS "
                "must be greater than zero."
            )

        return max_age

    @classmethod
    def build_connect_link(cls, user) -> TelegramConnectLink:
        bot_username = str(
            settings.NOTIF_TELEGRAM_BOT_USERNAME
        ).strip().lstrip("@")

        if not bot_username:
            raise TelegramOnboardingError(
                "NOTIF_TELEGRAM_BOT_USERNAME is empty"
            )

        token = cls._build_token(
            user_id=str(user.pk),
        )

        url = (
            f"https://t.me/{bot_username}"
            f"?start={token}"
        )

        return TelegramConnectLink(
            token=token,
            url=url,
            expires_in_seconds=(
                cls._get_token_max_age_seconds()
            ),
        )

    @classmethod
    def connect_chat(
        cls,
        token: str,
        telegram_chat_id: str,
    ) -> NotificationChannel:
        user_id = cls._verify_token(
            token=token,
        )

        User = get_user_model()

        user = User.objects.filter(
            pk=user_id,
        ).first()

        if user is None:
            raise TelegramOnboardingError(
                "Пользователь не найден."
            )

        normalized_chat_id = str(
            telegram_chat_id
        ).strip()

        if not normalized_chat_id:
            raise TelegramOnboardingError(
                "Telegram chat ID отсутствует."
            )

        NotificationChannel.objects.filter(
            type=NotificationChannel.ChannelType.TELEGRAM,
            telegram_chat_id=normalized_chat_id,
        ).exclude(
            user=user,
        ).update(
            is_active=False,
        )

        channel, _ = (
            NotificationChannel.objects.update_or_create(
                user=user,
                type=NotificationChannel.ChannelType.TELEGRAM,
                telegram_chat_id=normalized_chat_id,
                defaults={
                    "is_active": True,
                    "email": "",
                    "webhook_url": "",
                },
            )
        )

        return channel

    @classmethod
    def _build_token(
        cls,
        *,
        user_id: str,
    ) -> str:
        issued_at = int(
            time.time()
        )

        payload = (
            f"{user_id}:{issued_at}"
        ).encode("utf-8")

        encoded_payload = cls._encode_base64url(
            payload
        )

        signature = cls._build_signature(
            encoded_payload
        )

        token = (
            f"{encoded_payload}"
            f"{signature}"
        )

        if len(token) > TELEGRAM_START_TOKEN_MAX_LENGTH:
            raise TelegramOnboardingError(
                "Не удалось создать короткий Telegram-токен."
            )

        return token

    @classmethod
    def _verify_token(
        cls,
        *,
        token: str,
    ) -> str:
        normalized_token = str(
            token
        ).strip()

        if (
            not normalized_token
            or len(normalized_token)
            > TELEGRAM_START_TOKEN_MAX_LENGTH
        ):
            raise TelegramOnboardingError(
                "Некорректная ссылка подключения."
            )

        if len(normalized_token) <= (
            TELEGRAM_START_TOKEN_SIGNATURE_LENGTH
        ):
            raise TelegramOnboardingError(
                "Некорректная ссылка подключения."
            )

        encoded_payload = normalized_token[
            :-TELEGRAM_START_TOKEN_SIGNATURE_LENGTH
        ]
        received_signature = normalized_token[
            -TELEGRAM_START_TOKEN_SIGNATURE_LENGTH:
        ]

        expected_signature = cls._build_signature(
            encoded_payload
        )

        if not hmac.compare_digest(
            received_signature,
            expected_signature,
        ):
            raise TelegramOnboardingError(
                "Некорректная ссылка подключения."
            )

        try:
            decoded_payload = (
                cls._decode_base64url(
                    encoded_payload
                )
                .decode("utf-8")
            )

            user_id, issued_at_raw = (
                decoded_payload.split(
                    ":",
                    maxsplit=1,
                )
            )

            issued_at = int(
                issued_at_raw
            )

        except (
            UnicodeDecodeError,
            ValueError,
        ) as exc:
            raise TelegramOnboardingError(
                "Некорректная ссылка подключения."
            ) from exc

        if not user_id:
            raise TelegramOnboardingError(
                "В токене отсутствует user_id."
            )

        current_timestamp = int(
            time.time()
        )

        if issued_at > current_timestamp + 60:
            raise TelegramOnboardingError(
                "Некорректная ссылка подключения."
            )

        token_age = (
            current_timestamp - issued_at
        )

        if token_age > cls._get_token_max_age_seconds():
            raise TelegramOnboardingError(
                "Ссылка подключения устарела."
            )

        return user_id

    @classmethod
    def _build_signature(
        cls,
        encoded_payload: str,
    ) -> str:
        digest = salted_hmac(
            key_salt=cls._get_signing_salt(),
            value=encoded_payload,
            secret=settings.SECRET_KEY,
            algorithm="sha256",
        ).digest()

        shortened_digest = digest[
            :TELEGRAM_START_TOKEN_SIGNATURE_BYTES
        ]

        return cls._encode_base64url(
            shortened_digest
        )

    @staticmethod
    def _encode_base64url(
        value: bytes,
    ) -> str:
        return (
            base64.urlsafe_b64encode(
                value
            )
            .rstrip(b"=")
            .decode("ascii")
        )

    @staticmethod
    def _decode_base64url(
        value: str,
    ) -> bytes:
        padding_length = (
            -len(value)
        ) % 4

        padded_value = (
            value
            + "=" * padding_length
        )

        return base64.urlsafe_b64decode(
            padded_value.encode("ascii")
        )
