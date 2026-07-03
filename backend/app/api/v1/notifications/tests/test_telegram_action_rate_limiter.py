from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from app.api.v1.notifications.telegram.action_rate_limiter import (
    TelegramActionRateLimiter,
)


class TelegramActionRateLimiterTests(SimpleTestCase):
    @patch(
        "app.api.v1.notifications.telegram.action_rate_limiter."
        "check_rate_limit"
    )
    def test_uses_separate_keys_for_each_action(
        self,
        check_rate_limit_mock,
    ) -> None:
        check_rate_limit_mock.return_value = SimpleNamespace(
            allowed=True,
            limit=10,
            remaining=9,
            retry_after_seconds=0,
        )
        limiter = TelegramActionRateLimiter(
            preview_limit=5,
            preview_window_seconds=60,
            check_now_limit=3,
            check_now_window_seconds=60,
            callback_limit=30,
            callback_window_seconds=60,
        )

        limiter.check_preview(user_id=7)
        limiter.check_check_now(user_id=7)
        limiter.check_callback(telegram_user_id=123)

        calls = check_rate_limit_mock.call_args_list
        self.assertEqual(
            calls[0].kwargs,
            {
                "key": "telegram_bot:preview:7",
                "limit": 5,
                "window_seconds": 60,
            },
        )
        self.assertEqual(
            calls[1].kwargs,
            {
                "key": "telegram_bot:check_now:7",
                "limit": 3,
                "window_seconds": 60,
            },
        )
        self.assertEqual(
            calls[2].kwargs,
            {
                "key": "telegram_bot:callback:123",
                "limit": 30,
                "window_seconds": 60,
            },
        )

    @patch(
        "app.api.v1.notifications.telegram.action_rate_limiter."
        "check_rate_limit"
    )
    def test_returns_retry_after_when_blocked(
        self,
        check_rate_limit_mock,
    ) -> None:
        check_rate_limit_mock.return_value = SimpleNamespace(
            allowed=False,
            limit=3,
            remaining=0,
            retry_after_seconds=17,
        )
        limiter = TelegramActionRateLimiter()

        result = limiter.check_check_now(user_id=7)

        self.assertFalse(result.allowed)
        self.assertEqual(result.retry_after_seconds, 17)
        self.assertEqual(result.limit, 3)

    @patch(
        "app.api.v1.notifications.telegram.action_rate_limiter."
        "check_rate_limit"
    )
    def test_fails_open_when_redis_check_raises(
        self,
        check_rate_limit_mock,
    ) -> None:
        check_rate_limit_mock.side_effect = RuntimeError(
            "Redis unavailable"
        )
        limiter = TelegramActionRateLimiter()

        result = limiter.check_callback(
            telegram_user_id=123,
        )

        self.assertTrue(result.allowed)
        self.assertEqual(result.retry_after_seconds, 0)
