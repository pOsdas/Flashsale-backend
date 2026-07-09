from dataclasses import dataclass

from app.api.v1.common.rate_limit import check_rate_limit
from app.api.v1.notifications.telegram.telegram_metrics import (
    TELEGRAM_RATE_LIMIT_DECISIONS_TOTAL,
)
from app.core.logging import get_logger


logger = get_logger(__name__)

DEFAULT_PREVIEW_RATE_LIMIT = 5
DEFAULT_PREVIEW_RATE_LIMIT_WINDOW_SECONDS = 60
DEFAULT_CHECK_NOW_RATE_LIMIT = 3
DEFAULT_CHECK_NOW_RATE_LIMIT_WINDOW_SECONDS = 60
DEFAULT_CALLBACK_RATE_LIMIT = 30
DEFAULT_CALLBACK_RATE_LIMIT_WINDOW_SECONDS = 60


@dataclass(frozen=True, slots=True)
class TelegramActionRateLimitDecision:
    allowed: bool
    retry_after_seconds: int
    limit: int
    window_seconds: int


class TelegramActionRateLimiter:
    """Redis-backed limits for user-triggered Telegram bot actions."""

    def __init__(
        self,
        *,
        preview_limit: int = DEFAULT_PREVIEW_RATE_LIMIT,
        preview_window_seconds: int = (
            DEFAULT_PREVIEW_RATE_LIMIT_WINDOW_SECONDS
        ),
        check_now_limit: int = DEFAULT_CHECK_NOW_RATE_LIMIT,
        check_now_window_seconds: int = (
            DEFAULT_CHECK_NOW_RATE_LIMIT_WINDOW_SECONDS
        ),
        callback_limit: int = DEFAULT_CALLBACK_RATE_LIMIT,
        callback_window_seconds: int = (
            DEFAULT_CALLBACK_RATE_LIMIT_WINDOW_SECONDS
        ),
    ) -> None:
        self.preview_limit = self._normalize_positive_int(
            preview_limit,
            fallback=DEFAULT_PREVIEW_RATE_LIMIT,
        )
        self.preview_window_seconds = self._normalize_positive_int(
            preview_window_seconds,
            fallback=DEFAULT_PREVIEW_RATE_LIMIT_WINDOW_SECONDS,
        )
        self.check_now_limit = self._normalize_positive_int(
            check_now_limit,
            fallback=DEFAULT_CHECK_NOW_RATE_LIMIT,
        )
        self.check_now_window_seconds = self._normalize_positive_int(
            check_now_window_seconds,
            fallback=DEFAULT_CHECK_NOW_RATE_LIMIT_WINDOW_SECONDS,
        )
        self.callback_limit = self._normalize_positive_int(
            callback_limit,
            fallback=DEFAULT_CALLBACK_RATE_LIMIT,
        )
        self.callback_window_seconds = self._normalize_positive_int(
            callback_window_seconds,
            fallback=DEFAULT_CALLBACK_RATE_LIMIT_WINDOW_SECONDS,
        )

    def check_preview(
        self,
        *,
        user_id: int | str,
    ) -> TelegramActionRateLimitDecision:
        return self._check(
            scope="preview",
            identity=user_id,
            limit=self.preview_limit,
            window_seconds=self.preview_window_seconds,
        )

    def check_check_now(
        self,
        *,
        user_id: int | str,
    ) -> TelegramActionRateLimitDecision:
        return self._check(
            scope="check_now",
            identity=user_id,
            limit=self.check_now_limit,
            window_seconds=self.check_now_window_seconds,
        )

    def check_callback(
        self,
        *,
        telegram_user_id: int | str,
    ) -> TelegramActionRateLimitDecision:
        return self._check(
            scope="callback",
            identity=telegram_user_id,
            limit=self.callback_limit,
            window_seconds=self.callback_window_seconds,
        )

    def _check(
        self,
        *,
        scope: str,
        identity: int | str,
        limit: int,
        window_seconds: int,
    ) -> TelegramActionRateLimitDecision:
        normalized_identity = str(identity).strip()

        if not normalized_identity:
            TELEGRAM_RATE_LIMIT_DECISIONS_TOTAL.labels(
                scope=scope,
                result="allowed",
            ).inc()

            return TelegramActionRateLimitDecision(
                allowed=True,
                retry_after_seconds=0,
                limit=limit,
                window_seconds=window_seconds,
            )

        try:
            result = check_rate_limit(
                key=(
                    f"telegram_bot:{scope}:"
                    f"{normalized_identity}"
                ),
                limit=limit,
                window_seconds=window_seconds,
            )
        except Exception as exc:
            TELEGRAM_RATE_LIMIT_DECISIONS_TOTAL.labels(
                scope=scope,
                result="error_fail_open",
            ).inc()

            logger.exception(
                "Telegram action rate limit check failed open",
                extra={
                    "service": "telegram_bot",
                    "rate_limit_scope": scope,
                    "identity": normalized_identity,
                    "error": str(exc),
                },
            )
            return TelegramActionRateLimitDecision(
                allowed=True,
                retry_after_seconds=0,
                limit=limit,
                window_seconds=window_seconds,
            )

        retry_after_seconds = max(
            int(result.retry_after_seconds or 0),
            0,
        )

        decision = TelegramActionRateLimitDecision(
            allowed=bool(result.allowed),
            retry_after_seconds=retry_after_seconds,
            limit=int(result.limit),
            window_seconds=window_seconds,
        )

        TELEGRAM_RATE_LIMIT_DECISIONS_TOTAL.labels(
            scope=scope,
            result=(
                "allowed"
                if decision.allowed
                else "blocked"
            ),
        ).inc()

        if not decision.allowed:
            logger.warning(
                "Telegram action blocked by Redis rate limit",
                extra={
                    "service": "telegram_bot",
                    "rate_limit_scope": scope,
                    "identity": normalized_identity,
                    "limit": int(result.limit),
                    "remaining": int(result.remaining),
                    "window_seconds": window_seconds,
                    "retry_after_seconds": retry_after_seconds,
                },
            )

        return decision

    @staticmethod
    def _normalize_positive_int(
        value: int,
        *,
        fallback: int,
    ) -> int:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            return fallback

        if normalized < 1:
            return fallback

        return normalized
