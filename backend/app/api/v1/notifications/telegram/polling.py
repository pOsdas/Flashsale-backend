import signal
import time
from typing import Any

import httpx

from app.api.v1.notifications.telegram.client import TelegramBotClient
from app.api.v1.notifications.telegram.router import TelegramUpdateRouter
from app.api.v1.notifications.telegram.telegram_metrics import (
    TELEGRAM_BOT_RUNNING,
    TELEGRAM_HANDLER_ERRORS_TOTAL,
    TELEGRAM_LAST_UPDATE_TIMESTAMP_SECONDS,
    TELEGRAM_POLLING_HEARTBEAT_TIMESTAMP_SECONDS,
    TELEGRAM_POLLING_REQUEST_DURATION_SECONDS,
    TELEGRAM_POLLING_REQUESTS_TOTAL,
    TELEGRAM_UPDATES_IN_PROGRESS,
    TELEGRAM_UPDATES_TOTAL,
)
from app.core.logging import get_logger


logger = get_logger(__name__)


class TelegramPollingRunner:
    def __init__(
        self,
        *,
        client: TelegramBotClient,
        router: TelegramUpdateRouter,
        drop_pending_updates_on_start: bool,
        error_sleep_seconds: int = 5,
    ) -> None:
        self.client = client
        self.router = router
        self.drop_pending_updates_on_start = (
            drop_pending_updates_on_start
        )
        self.error_sleep_seconds = error_sleep_seconds
        self.should_stop = False

    def run(self) -> None:
        self._register_signal_handlers()
        offset: int | None = None

        TELEGRAM_BOT_RUNNING.set(1)

        logger.info(
            "Telegram bot polling started",
            extra={
                "service": "telegram_bot",
                "drop_pending_updates_on_start": (
                    self.drop_pending_updates_on_start
                ),
            },
        )

        try:
            if self.drop_pending_updates_on_start:
                self.client.drop_pending_updates()

                logger.info(
                    "Telegram pending updates dropped",
                    extra={
                        "service": "telegram_bot",
                    },
                )

            while not self.should_stop:
                polling_started_at = time.monotonic()

                try:
                    updates = self.client.get_updates(
                        offset=offset,
                    )

                except httpx.HTTPError as exc:
                    TELEGRAM_POLLING_REQUESTS_TOTAL.labels(
                        status="http_error",
                    ).inc()
                    TELEGRAM_HANDLER_ERRORS_TOTAL.labels(
                        stage="polling_http",
                    ).inc()

                    logger.exception(
                        "Telegram bot HTTP error",
                        extra={
                            "service": "telegram_bot",
                            "error": str(exc),
                        },
                    )
                    time.sleep(self.error_sleep_seconds)

                except Exception as exc:
                    TELEGRAM_POLLING_REQUESTS_TOTAL.labels(
                        status="error",
                    ).inc()
                    TELEGRAM_HANDLER_ERRORS_TOTAL.labels(
                        stage="polling",
                    ).inc()

                    logger.exception(
                        "Telegram bot polling error",
                        extra={
                            "service": "telegram_bot",
                            "error": str(exc),
                        },
                    )
                    time.sleep(self.error_sleep_seconds)

                else:
                    TELEGRAM_POLLING_REQUESTS_TOTAL.labels(
                        status="success",
                    ).inc()
                    TELEGRAM_POLLING_HEARTBEAT_TIMESTAMP_SECONDS.set(
                        time.time()
                    )

                    offset = self._process_updates(
                        updates=updates,
                        current_offset=offset,
                    )

                finally:
                    TELEGRAM_POLLING_REQUEST_DURATION_SECONDS.observe(
                        time.monotonic() - polling_started_at
                    )

        finally:
            TELEGRAM_BOT_RUNNING.set(0)
            self.client.close()

            logger.info(
                "Telegram bot polling stopped",
                extra={
                    "service": "telegram_bot",
                },
            )

    def stop(self) -> None:
        self.should_stop = True

    def _process_updates(
        self,
        *,
        updates: list[dict[str, Any]],
        current_offset: int | None,
    ) -> int | None:
        offset = current_offset

        for update in updates:
            if self.should_stop:
                break

            update_type = self._get_update_type(
                update=update,
            )
            update_id = update.get("update_id")

            if not isinstance(update_id, int):
                TELEGRAM_UPDATES_TOTAL.labels(
                    update_type=update_type,
                    status="ignored",
                ).inc()

                logger.warning(
                    "Telegram update without valid update_id ignored",
                    extra={
                        "service": "telegram_bot",
                        "update": update,
                    },
                )
                continue

            next_offset = update_id + 1
            TELEGRAM_UPDATES_IN_PROGRESS.inc()

            try:
                self.router.handle_update(
                    update=update,
                )
                TELEGRAM_UPDATES_TOTAL.labels(
                    update_type=update_type,
                    status="processed",
                ).inc()

            except Exception as exc:
                TELEGRAM_UPDATES_TOTAL.labels(
                    update_type=update_type,
                    status="error",
                ).inc()
                TELEGRAM_HANDLER_ERRORS_TOTAL.labels(
                    stage="update",
                ).inc()

                logger.exception(
                    "Telegram update handling failed",
                    extra={
                        "service": "telegram_bot",
                        "update_id": update_id,
                        "error": str(exc),
                    },
                )

            finally:
                TELEGRAM_UPDATES_IN_PROGRESS.dec()
                TELEGRAM_LAST_UPDATE_TIMESTAMP_SECONDS.set(
                    time.time()
                )
                offset = next_offset

        return offset

    def _register_signal_handlers(self) -> None:
        signal.signal(
            signal.SIGINT,
            self._handle_stop_signal,
        )
        signal.signal(
            signal.SIGTERM,
            self._handle_stop_signal,
        )

    def _handle_stop_signal(
        self,
        signum,
        frame,
    ) -> None:
        self.stop()

        logger.info(
            "Telegram bot polling stopping",
            extra={
                "service": "telegram_bot",
                "signal": signum,
            },
        )

    @staticmethod
    def _get_update_type(
        *,
        update: dict[str, Any],
    ) -> str:
        if update.get("callback_query"):
            return "callback_query"

        if update.get("message"):
            return "message"

        return "other"
