class PaymentServiceError(Exception):
    """Базовая ошибка сервиса платежей."""


class OrderNotFoundError(PaymentServiceError):
    """Заказ не был найден."""


class InvalidOrderForPaymentError(PaymentServiceError):
    """Заказ не может быть оплачен."""


class PaymentNotFoundError(PaymentServiceError):
    """Платеж не был найден."""


class InvalidPaymentWebhookError(PaymentServiceError):
    """Webhook имеет невалидный payload."""
