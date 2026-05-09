class FetcherError(Exception):
    """Базовая ошибка сервиса fetcher."""


class FetcherValidationError(FetcherError):
    """Входящий payload невалидный (business-level валидация)."""


class FetcherImportInProgressError(FetcherError):
    """Импорт по данному ресурсу уже занят (Redis lock)."""


class FetcherBatchAlreadyProcessedError(FetcherError):
    """Подобный batch_id уже был обработан (idempotency)."""


class FetcherUpsertError(FetcherError):
    """Product/stock upsert не удался."""


class FetcherStockUpdateError(FetcherError):
    """Обновление stock не удалось."""


class FetcherCurrencyNotSupportedError(FetcherError):
    """Валюта не поддерживается системой."""
