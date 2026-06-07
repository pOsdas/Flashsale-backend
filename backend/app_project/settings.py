import os
import logging.config
from pathlib import Path

import dj_database_url

import app.core.logging_filters
from app.core.config import get_settings

# Base project dir
BASE_DIR = Path(__file__).resolve().parent

s = get_settings()

# Основные настройки
SECRET_KEY = s.secret_key
DEBUG = s.debug
ALLOWED_HOSTS = s.allowed_hosts

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Internationalization
LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Amsterdam"
USE_I18N = True
USE_TZ = True

# Applications
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_prometheus',

    # for webhooks
    'rest_framework',
    "drf_spectacular",

    "app.api.v1.common.apps.V1CommonConfig",
    "app.api.v1.catalog.apps.V1CatalogConfig",
    "app.api.v1.orders.apps.V1OrdersConfig",
    "app.api.v1.payments.apps.V1PaymentsConfig",
    "app.api.v1.monitoring.apps.V1MonitoringConfig",
]
# Middleware
MIDDLEWARE = [
    'django_prometheus.middleware.PrometheusBeforeMiddleware',
    'app.core.middleware.request_id.RequestIDMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_prometheus.middleware.PrometheusAfterMiddleware',
]

ROOT_URLCONF = 'app_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # 'DIRS': [BASE_DIR / 'templates'],
        "DIRS": [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

ASGI_APPLICATION = 'app_project.asgi.application'
WSGI_APPLICATION = 'app_project.wsgi.application'

# Database
DATABASES = {
    'default': dj_database_url.parse(
        s.database_url,
        conn_max_age=60,
        ssl_require=False,
    )
}

# Static
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'static'

# Redis / Celery
REDIS_URL = str(s.redis_url)

CELERY_BROKER_URL = str(s.celery_broker_url)
if s.celery_result_backend is not None:
    CELERY_RESULT_BACKEND = str(s.celery_result_backend)

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# Go Fetcher
MONITORING_FETCHER_MODE = os.getenv("MONITORING_FETCHER_MODE", default="fake")

GO_FETCHER_BASE_URL = os.getenv("GO_FETCHER_BASE_URL", default="http://localhost:8090")
GO_FETCHER_PRODUCT_ENDPOINT = os.getenv(
    "GO_FETCHER_PRODUCT_ENDPOINT",
    default="/api/v1/fetch/product",
)
GO_FETCHER_API_KEY = os.getenv("GO_FETCHER_API_KEY", default="")
GO_FETCHER_TIMEOUT_SECONDS = int(os.getenv("GO_FETCHER_TIMEOUT_SECONDS", default=20))

# RabbitMQ
OUTBOX_DISPATCH_MODE = os.getenv("OUTBOX_DISPATCH_MODE", default="local")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", default="amqp://guest:guest@localhost:5672/")
RABBITMQ_EXCHANGE = os.getenv("RABBITMQ_EXCHANGE", default="flashsale.events")

# Security
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # if Nginx/Ingress
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
else:
    SECURE_SSL_REDIRECT = False

# Passwords
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher'
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# DRF for webhook
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
}


SPECTACULAR_SETTINGS = {
    "TITLE": "Flashsale Backend API",
    "DESCRIPTION": "API documentation for flashsale-backend",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,

    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": True,
    },
}

# Webhooks / Go fetcher
STRIPE_WEBHOOK_SECRET = getattr(s, "stripe_webhook_secret", "dev_stripe_webhook_secret")
FETCHER_QUEUE_KEY = getattr(s, "fetcher_queue_key", "fetcher:queue")
FETCHER_RESULT_PREFIX = getattr(s, "fetcher_result_prefix", "fetcher:result:")

# Logging
LOG_FORMAT = os.getenv("LOG_FORMAT", default="colored")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "colored": {
            "()": "colorlog.ColoredFormatter",
            "format": "%(log_color)s%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "log_colors": {
                "DEBUG": "cyan",
                "INFO": "white",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        },
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "fmt": (
                "%(asctime)s "
                "%(levelname)s "
                "%(name)s "
                "%(module)s "
                "%(funcName)s "
                "%(lineno)d "
                "%(message)s "
                "%(service)s "
                "%(request_id)s "
                "%(method)s "
                "%(path)s "
                "%(status_code)s "
                "%(duration_ms)s "
                "%(event_id)s "
                "%(topic)s "
                "%(attempts)s "
                "%(error)s"
            ),
        },
    },
    "filters": {
        "request_id": {
            "()": "app.core.logging_filters.RequestIdLoggingFilter"
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "json" if LOG_FORMAT == "json" else "colored",
            "level": "DEBUG",
            "filters": ["request_id"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "outbox": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

logging.config.dictConfig(LOGGING)