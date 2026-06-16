from dataclasses import dataclass


@dataclass
class Product:
    sku: str = ""
    title: str = ""
    seller_name: str = ""
    brand: str = ""
    price_cents: int = 0
    currency: str = "RUB"
    available: int = 0
    is_active: bool = True
    rating: float = 0.0
    reviews_count: int = 0
