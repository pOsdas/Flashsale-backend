import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from django.conf import settings
from django.db import connections
from django.db.utils import OperationalError

from app.core.logging import get_logger


logger = get_logger(__name__)


@dataclass(frozen=True)
class HealthCheckResult:
    name: str
    status: str
    details: dict[str, Any]


class SystemHealthChecker:
    STATUS_OK = "ok"
    STATUS_ERROR = "error"
    STATUS_WARNING = "warning"

    def run(self) -> dict[str, Any]:
        checks = [
            self._check_database(),
            self._check_redis(),
            self._check_rabbitmq(),
            self._check_go_fetcher(),
            self._check_telegram_config(),
        ]

        overall_status = self._build_overall_status(checks)

        return {
            "status": overall_status,
            "checks": {
                check.name: {
                    "status": check.status,
                    "details": check.details,
                }
                for check in checks
            },
        }

    def _build_overall_status(self, checks: list[HealthCheckResult]) -> str:
        if any(check.status == self.STATUS_ERROR for check in checks):
            return "unhealthy"

        if any(check.status == self.STATUS_WARNING for check in checks):
            return "degraded"

        return "healthy"

    def _check_database(self) -> HealthCheckResult:
        try:
            connection = connections["default"]
            connection.ensure_connection()

            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                cursor.fetchone()

            return HealthCheckResult(
                name="database",
                status=self.STATUS_OK,
                details={
                    "engine": connection.settings_dict.get("ENGINE", ""),
                    "name": connection.settings_dict.get("NAME", ""),
                    "host": connection.settings_dict.get("HOST", ""),
                    "port": connection.settings_dict.get("PORT", ""),
                },
            )

        except OperationalError as exc:
            logger.exception(
                "Database health check failed",
                extra={
                    "service": "system_health",
                    "check": "database",
                    "error": str(exc),
                },
            )

            return HealthCheckResult(
                name="database",
                status=self.STATUS_ERROR,
                details={
                    "error": str(exc),
                },
            )

        except Exception as exc:
            logger.exception(
                "Unexpected database health check error",
                extra={
                    "service": "system_health",
                    "check": "database",
                    "error": str(exc),
                },
            )

            return HealthCheckResult(
                name="database",
                status=self.STATUS_ERROR,
                details={
                    "error": str(exc),
                },
            )

    def _check_redis(self) -> HealthCheckResult:
        redis_url = self._get_redis_url()

        if not redis_url:
            return HealthCheckResult(
                name="redis",
                status=self.STATUS_WARNING,
                details={
                    "error": "Redis URL is not configured.",
                },
            )

        try:
            import redis

            client = redis.Redis.from_url(
                redis_url,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            pong = client.ping()

            return HealthCheckResult(
                name="redis",
                status=self.STATUS_OK if pong else self.STATUS_ERROR,
                details={
                    "url": self._mask_url(redis_url),
                    "ping": bool(pong),
                },
            )

        except Exception as exc:
            logger.exception(
                "Redis health check failed",
                extra={
                    "service": "system_health",
                    "check": "redis",
                    "error": str(exc),
                },
            )

            return HealthCheckResult(
                name="redis",
                status=self.STATUS_ERROR,
                details={
                    "url": self._mask_url(redis_url),
                    "error": str(exc),
                },
            )

    def _check_rabbitmq(self) -> HealthCheckResult:
        rabbitmq_url = self._get_rabbitmq_url()

        if not rabbitmq_url:
            return HealthCheckResult(
                name="rabbitmq",
                status=self.STATUS_WARNING,
                details={
                    "error": "RabbitMQ URL is not configured.",
                },
            )

        parsed_url = urlparse(rabbitmq_url)

        host = parsed_url.hostname
        port = parsed_url.port or 5672

        if not host:
            return HealthCheckResult(
                name="rabbitmq",
                status=self.STATUS_ERROR,
                details={
                    "url": self._mask_url(rabbitmq_url),
                    "error": "RabbitMQ host is empty.",
                },
            )

        try:
            with socket.create_connection(
                (host, port),
                timeout=2,
            ):
                pass

            return HealthCheckResult(
                name="rabbitmq",
                status=self.STATUS_OK,
                details={
                    "host": host,
                    "port": port,
                    "url": self._mask_url(rabbitmq_url),
                },
            )

        except OSError as exc:
            logger.exception(
                "RabbitMQ health check failed",
                extra={
                    "service": "system_health",
                    "check": "rabbitmq",
                    "host": host,
                    "port": port,
                    "error": str(exc),
                },
            )

            return HealthCheckResult(
                name="rabbitmq",
                status=self.STATUS_ERROR,
                details={
                    "host": host,
                    "port": port,
                    "url": self._mask_url(rabbitmq_url),
                    "error": str(exc),
                },
            )

    def _check_go_fetcher(self) -> HealthCheckResult:
        base_url = getattr(settings, "GO_FETCHER_BASE_URL", "")

        if not base_url:
            return HealthCheckResult(
                name="go_fetcher",
                status=self.STATUS_WARNING,
                details={
                    "error": "GO_FETCHER_BASE_URL is not configured.",
                },
            )

        health_url = f"{base_url.rstrip('/')}/health/"

        try:
            response = httpx.get(
                health_url,
                timeout=3,
            )

            if 200 <= response.status_code < 300:
                return HealthCheckResult(
                    name="go_fetcher",
                    status=self.STATUS_OK,
                    details={
                        "url": health_url,
                        "status_code": response.status_code,
                    },
                )

            return HealthCheckResult(
                name="go_fetcher",
                status=self.STATUS_ERROR,
                details={
                    "url": health_url,
                    "status_code": response.status_code,
                    "response": response.text[:500],
                },
            )

        except httpx.RequestError as exc:
            logger.exception(
                "go_fetcher health check failed",
                extra={
                    "service": "system_health",
                    "check": "go_fetcher",
                    "url": health_url,
                    "error": str(exc),
                },
            )

            return HealthCheckResult(
                name="go_fetcher",
                status=self.STATUS_ERROR,
                details={
                    "url": health_url,
                    "error": str(exc),
                },
            )

    def _check_telegram_config(self) -> HealthCheckResult:
        bot_token = getattr(settings, "NOTIF_TELEGRAM_BOT_TOKEN", "")

        if not bot_token:
            bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")

        if not bot_token:
            return HealthCheckResult(
                name="telegram",
                status=self.STATUS_WARNING,
                details={
                    "configured": False,
                    "error": "Telegram bot token is not configured.",
                },
            )

        return HealthCheckResult(
            name="telegram",
            status=self.STATUS_OK,
            details={
                "configured": True,
            },
        )

    def _get_redis_url(self) -> str:
        redis_url = getattr(settings, "REDIS_URL", "")

        if redis_url:
            return redis_url

        celery_broker_url = getattr(settings, "CELERY_BROKER_URL", "")

        if celery_broker_url and celery_broker_url.startswith("redis"):
            return celery_broker_url

        return ""

    def _get_rabbitmq_url(self) -> str:
        possible_setting_names = [
            "RABBITMQ_URL",
            "OUTBOX_RABBITMQ_URL",
            "NOTIFICATION_RABBITMQ_URL",
            "CELERY_BROKER_URL",
        ]

        for setting_name in possible_setting_names:
            value = getattr(settings, setting_name, "")

            if value and value.startswith("amqp"):
                return value

        host = getattr(settings, "RABBITMQ_HOST", "")

        if host:
            port = getattr(settings, "RABBITMQ_PORT", 5672)
            username = getattr(settings, "RABBITMQ_USER", "guest")
            password = getattr(settings, "RABBITMQ_PASSWORD", "guest")
            virtual_host = getattr(settings, "RABBITMQ_VHOST", "/")

            return f"amqp://{username}:{password}@{host}:{port}/{virtual_host}"

        return ""

    def _mask_url(self, url: str) -> str:
        parsed_url = urlparse(url)

        if not parsed_url.username and not parsed_url.password:
            return url

        hostname = parsed_url.hostname or ""
        port = f":{parsed_url.port}" if parsed_url.port else ""

        username = parsed_url.username or ""

        masked_auth = username

        if parsed_url.password:
            masked_auth = f"{username}:***"

        netloc = f"{masked_auth}@{hostname}{port}"

        return parsed_url._replace(
            netloc=netloc,
        ).geturl()
