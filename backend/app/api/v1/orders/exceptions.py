class OrderServiceError(Exception):
    """Базовая ошибка сервиса заказов."""


class EmptyOrderError(OrderServiceError):
    """Заказ не может быть пустым."""


class InvalidOrderItemQuantityError(OrderServiceError):
    """Количество товара должно быть положительным."""


class ProductNotFoundError(OrderServiceError):
    """Товар не найден."""


class ProductInactiveError(OrderServiceError):
    """Товар неактивен."""


class InsufficientStockError(OrderServiceError):
    """Недостаточно товара на складе."""


class OrderNotFoundError(OrderServiceError):
    """Заказ не найден."""


class UnsupportedCurrencyError(OrderServiceError):
    """Неподдерживаемая валюта."""


class InvalidOrderStatusTransitionError(OrderServiceError):
    """Недопустимый переход статуса заказа."""


class IdempotencyConflictError(OrderServiceError):
    """Один и тот же idempotency key был использован с другим payload."""


class IdempotencyResultCorruptedError(OrderServiceError):
    """По idempotency key найден результат, но он некорректен."""