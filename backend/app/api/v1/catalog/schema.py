from typing import List, Optional
import strawberry
from graphql import GraphQLError
from strawberry import auto
from strawberry.types import Info
from strawberry_django import type as dj_type

from app.api.v1.catalog.models import Stock, Product
from app.api.v1.catalog.exceptions import ProductNotFoundError, CatalogError
from app.api.v1.catalog.selectors import (
    list_products, get_product_by_sku,
    ProductListFilters, Pagination,
)
from app.api.v1.catalog.services import set_stock, create_product


# ---- Types ----
@dj_type(Product)
class ProductType:
    id: auto
    sku: auto
    title: auto
    price_cents: auto
    currency: auto
    is_active: auto

    stock: Optional["StockType"]


@dj_type(Stock)
class StockType:
    id: auto
    product: auto
    available: auto


# ---- Query ----
@strawberry.type
class CatalogQuery:
    @strawberry.field
    def product(self, info: Info, sku: str, only_active: bool = True) -> ProductType:
        try:
            return get_product_by_sku(  # type: ignore
                product_sku=sku,
                only_active=only_active,
            )
        except ProductNotFoundError as e:
            raise GraphQLError(str(e))


    @strawberry.field
    def products(
            self,
            info: Info,
            is_active: Optional[bool] = None,
            search: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> List[ProductType]:
        try:
            queryset = list_products(
                filters=ProductListFilters(
                    is_active=is_active,
                    search=search,
                ),
                pagination=Pagination(
                    limit=limit,
                    offset=offset,
                )
            )
        except ValueError as e:
            raise GraphQLError(str(e))

        return list(queryset)


# ---- Inputs ----
@strawberry.input
class ProductCreateInput:
    sku: str
    title: str
    price_cents: int
    currency: str = "EUR"
    is_active: bool = True
    available: int = 0


@strawberry.input
class StockSetInput:
    sku: str
    available: int


# ---- Mutations ----
@strawberry.type
class CatalogMutation:
    @strawberry.mutation
    def create_product(self, info: Info, data: ProductCreateInput) -> ProductType:
        try:
            return create_product(  # type: ignore
                product_sku=data.sku,
                title=data.title,
                price_cents=data.price_cents,
                currency=data.currency,
                is_active=data.is_active,
                available=data.available,
            )
        except CatalogError as e:
            raise GraphQLError(str(e)) from e

    @strawberry.mutation
    def set_stock(self, info: Info, data: StockSetInput) -> ProductType:
        try:
            return set_stock(  # type: ignore
                product_sku=data.sku,
                available=data.available
            )
        except CatalogError as e:
            raise GraphQLError(str(e)) from e
