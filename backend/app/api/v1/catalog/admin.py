from django.contrib import admin

from app.api.v1.catalog.models import Product, Stock


class StockInline(admin.TabularInline):
    model = Stock
    extra = 0
    fields = (
        "available",
    )
    readonly_fields = (
        "available",
    )
    can_delete = False
    max_num = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "sku",
        "title",
        "price_cents",
        "currency",
        "is_active",
        "stock_available",
    )
    list_filter = (
        "currency",
        "is_active",
    )
    search_fields = (
        "sku",
        "title",
    )
    ordering = ("id",)
    readonly_fields = (
        "id",
        "sku",
        "title",
        "price_cents",
        "currency",
        "is_active",
    )
    fields = (
        "id",
        "sku",
        "title",
        "price_cents",
        "currency",
        "is_active",
    )
    inlines = [StockInline]

    @admin.display(description="Available")
    def stock_available(self, obj: Product) -> int | None:
        if hasattr(obj, "stock"):
            return obj.stock.available
        return None


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "available",
    )
    list_filter = (
        "available",
    )
    search_fields = (
        "product__sku",
        "product__title",
    )
    ordering = ("-id",)
    readonly_fields = (
        "id",
        "product",
        "available",
    )


