class CatalogError(Exception):
    """Базовая ошибка каталога."""


class ProductNotFoundError(CatalogError):
    """Товар не найден."""


class ProductAlreadyExistsError(CatalogError):
    """Товар с подобным sku уже существует."""


class InvalidProductDataError(CatalogError):
    """ProductInputData не валидна."""
