from django.contrib import admin

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = (
        "product_name", "plan_name", "unit_price", "quantity",
        "stock_item", "expires_at",
    )
    autocomplete_fields = ("stock_item",)
    readonly_fields = ("product_name", "plan_name", "unit_price", "quantity")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id", "short_uuid", "user", "email", "status", "channel",
        "total", "currency", "created_at",
    )
    list_filter = ("status", "channel", "payment_provider", "created_at")
    search_fields = (
        "uuid", "email", "phone", "telegram_username", "payment_reference",
        "user__username", "user__email",
    )
    autocomplete_fields = ("user",)
    readonly_fields = ("uuid", "created_at", "paid_at", "delivered_at", "total")
    inlines = [OrderItemInline]
    date_hierarchy = "created_at"


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product_name", "plan_name", "unit_price", "quantity", "expires_at")
    search_fields = ("order__uuid", "product_name", "plan_name")
    autocomplete_fields = ("order", "product", "plan", "stock_item")
