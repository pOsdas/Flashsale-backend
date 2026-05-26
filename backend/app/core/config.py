"""Pydantic settings here"""

import os
from functools import lru_cache
from pydantic import AnyUrl, Field
from typing import List, Tuple
from pydantic_settings import SettingsConfigDict, BaseSettings


class RunModel(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8010


class ApiV1Prefix(BaseSettings):
    prefix: str = "/v1"


class ApiPrefix(BaseSettings):
    prefix: str = "api"
    v1: ApiV1Prefix = ApiV1Prefix()


def _resolve_env_files() -> Tuple[str, ...]:
    explicit = os.getenv("ENV_FILE")
    if explicit:
        return (explicit,)

    return (".env.local-template", ".env.local")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_resolve_env_files(),
        case_sensitive=False,
        extra="ignore",
    )
    # ENV
    env: str = Field(default="dev", description="dev|stage|prod")

    # POSTGRES
    postgres_db: str = "flashsale"
    postgres_user: str = "user"
    postgres_password: str = "pwd"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    database_url_raw: str | None = Field(
        default=None,
        alias="DATABASE_URL",
    )

    # BACKEND
    debug: bool = False
    secret_key: str
    allowed_hosts: List[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1"]
    )
    fetcher_api_key: str

    django_settings_module: str = "app_project.settings"

    # REDIS
    redis_url: AnyUrl = "redis://localhost:6379/0"

    # CELERY
    celery_broker_url: AnyUrl = "redis://localhost:6379/1"
    celery_result_backend: AnyUrl | None = "redis://localhost:6379/2"

    # OUTBOX / METRICS
    outbox_metrics_port: int = 9100

    # ensure_db
    allow_db_create: bool = False
    postgres_maintenance_db: str = "postgres"
    db_create_retries: int = 5
    db_create_retry_delay: int = 2

    run: RunModel = RunModel()
    api: ApiPrefix = ApiPrefix()

    @property
    def database_url(self) -> str:
        if self.database_url_raw:
            return self.database_url_raw

        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
