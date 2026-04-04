from django.contrib import admin

from app.api.v1.orders.models import (
    Reservation,
    Order,
    OrderItem,
    IdempotencyKey,
    OutboxEvent,
)


class OrderItemInline(admin.TabularInline):
    model = OrderItem,
    extra = 0
    fields = (
        "product",
        "qty",
        "price_cents",
        "line_total_cents",
    )
    readonly_fields = (
        "product",
        "qty",
        "price_cents",
        "line_total_cents",
    )
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "status",
        "currency",
        "total_cents",
        "created_at",
    )
    list_filter = (
        "status",
        "currency",
        "created_at",
    )
    search_fields = (
        "id",
        "user__username",
        "user__email",
    )
    ordering = ("-created_at",)
    readonly_fields = (
        "user",
        "status",
        "currency",
        "total_cents",
        "created_at",
    )
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "product",
        "qty",
        "price_cents",
        "line_total_cents",
    )
    list_filter = (
        "order__status",
    )
    search_fields = (
        "order__id",
        "product__name",
        "product__sku",
    )
    readonly_fields = (
        "order",
        "product",
        "qty",
        "price_cents",
        "line_total_cents",
    )


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "product",
        "qty",
        "created_at",
    )
    list_filter = (
        "created_at",
    )
    search_fields = (
        "user__username",
        "user__email",
        "product__name",
        "product__sku",
    )
    ordering = ("-created_at",)
    readonly_fields = (
        "user",
        "product",
        "qty",
        "created_at",
    )


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "key",
        "created_at",
    )
    list_filter = (
        "created_at",
    )
    search_fields = (
        "user__username",
        "user__email",
        "key",
        "payload_hash",
    )
    ordering = ("-created_at",)
    readonly_fields = (
        "user",
        "key",
        "payload_hash",
        "response_json",
        "created_at",
    )


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "topic",
        "created_at",
        "published_at",
    )
    list_filter = (
        "topic",
        "created_at",
        "published_at",
    )
    search_fields = (
        "topic",
    )
    ordering = ("-created_at",)
    readonly_fields = (
        "topic",
        "payload",
        "created_at",
        "published_at",
    )