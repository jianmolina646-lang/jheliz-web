from django.contrib import admin
from django.utils import timezone
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from .models import Order, OrderItem


class OrderItemInline(TabularInline):
    model = OrderItem
    extra = 0
    fields = (
        "product_name", "plan_name", "unit_price", "quantity",
        "requested_profile_name", "requested_pin", "customer_notes",
        "stock_item", "delivered_credentials", "expires_at",
    )
    autocomplete_fields = ("stock_item",)
    readonly_fields = ("product_name", "plan_name", "unit_price", "quantity")


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = (
        "id", "short_uuid", "user", "email", "display_status", "channel",
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
    actions = ("mark_preparing", "mark_delivered")
    list_filter_submit = True
    compressed_fields = True

    @display(
        description="Estado",
        ordering="status",
        label={
            Order.Status.PENDING: "warning",
            Order.Status.PAID: "info",
            Order.Status.PREPARING: "info",
            Order.Status.DELIVERED: "success",
            Order.Status.CANCELED: "danger",
            Order.Status.FAILED: "danger",
            Order.Status.REFUNDED: "",
        },
    )
    def display_status(self, obj: Order):
        return obj.status, obj.get_status_display()

    @admin.action(description="Marcar como En preparaci\u00f3n")
    def mark_preparing(self, request, queryset):
        count = 0
        for order in queryset:
            order.status = Order.Status.PREPARING
            order.save(update_fields=["status"])
            count += 1
        self.message_user(request, f"{count} pedidos marcados como en preparaci\u00f3n.")

    @admin.action(description="Marcar como Entregado")
    def mark_delivered(self, request, queryset):
        count = 0
        for order in queryset:
            order.status = Order.Status.DELIVERED
            order.delivered_at = timezone.now()
            order.save(update_fields=["status", "delivered_at"])
            count += 1
        self.message_user(request, f"{count} pedidos marcados como entregados.")


@admin.register(OrderItem)
class OrderItemAdmin(ModelAdmin):
    list_display = (
        "order", "product_name", "plan_name",
        "requested_profile_name", "requested_pin",
        "unit_price", "quantity", "expires_at",
    )
    list_filter = ("product__category", "product")
    search_fields = (
        "order__uuid", "product_name", "plan_name",
        "requested_profile_name", "requested_pin",
    )
    autocomplete_fields = ("order", "product", "plan", "stock_item")
