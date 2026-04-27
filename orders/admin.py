from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from . import emails
from .models import Order, OrderItem, PaymentSettings


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
        "payment_provider", "total", "currency", "created_at",
    )
    list_filter = ("status", "channel", "payment_provider", "created_at")
    search_fields = (
        "uuid", "email", "phone", "telegram_username", "payment_reference",
        "user__username", "user__email",
    )
    autocomplete_fields = ("user",)
    readonly_fields = (
        "uuid", "created_at", "paid_at", "delivered_at", "total",
        "payment_proof_uploaded_at", "payment_proof_preview",
    )
    inlines = [OrderItemInline]
    date_hierarchy = "created_at"
    actions = ("mark_preparing", "mark_delivered", "confirm_yape_payment", "reject_yape_payment")
    list_filter_submit = True
    compressed_fields = True

    fieldsets = (
        ("Datos", {
            "fields": ("uuid", "user", "email", "phone", "telegram_username", "channel", "notes"),
        }),
        ("Pago", {
            "fields": (
                "status", "payment_provider", "payment_reference", "total", "currency",
                "payment_proof_preview", "payment_proof", "payment_proof_uploaded_at",
                "payment_rejection_reason",
            ),
        }),
        ("Timestamps", {
            "fields": ("created_at", "paid_at", "delivered_at"),
        }),
    )

    @display(
        description="Estado",
        ordering="status",
        label={
            Order.Status.PENDING: "warning",
            Order.Status.VERIFYING: "warning",
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

    @admin.display(description="Comprobante")
    def payment_proof_preview(self, obj: Order):
        if not obj.payment_proof:
            return "\u2014"
        return format_html(
            '<a href="{0}" target="_blank" rel="noopener">'
            '<img src="{0}" style="max-width:320px;max-height:420px;border-radius:8px;'
            'border:1px solid #334155" /></a>',
            obj.payment_proof.url,
        )

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

    @admin.action(description="\u2705 Confirmar pago Yape \u2192 En preparaci\u00f3n")
    def confirm_yape_payment(self, request, queryset):
        now = timezone.now()
        updated = 0
        skipped = 0
        for order in queryset:
            if order.payment_provider != "yape":
                skipped += 1
                continue
            if not order.payment_proof:
                skipped += 1
                continue
            order.status = Order.Status.PREPARING
            order.paid_at = order.paid_at or now
            order.payment_rejection_reason = ""
            order.save(update_fields=["status", "paid_at", "payment_rejection_reason"])
            emails.send_order_preparing(order)
            updated += 1
        if updated:
            self.message_user(
                request,
                f"{updated} pago(s) Yape confirmado(s). Se envi\u00f3 email al cliente.",
                level=messages.SUCCESS,
            )
        if skipped:
            self.message_user(
                request,
                f"{skipped} pedido(s) ignorado(s) (no son Yape o no tienen comprobante).",
                level=messages.WARNING,
            )

    @admin.action(description="\u274c Rechazar comprobante Yape")
    def reject_yape_payment(self, request, queryset):
        updated = 0
        for order in queryset:
            if order.payment_provider != "yape":
                continue
            if not order.payment_rejection_reason:
                order.payment_rejection_reason = (
                    "No pudimos verificar el comprobante. Por favor sube una captura m\u00e1s clara "
                    "donde se vea el monto y el destinatario."
                )
            order.status = Order.Status.PENDING
            order.save(update_fields=["status", "payment_rejection_reason"])
            emails.send_yape_proof_rejected(order)
            updated += 1
        self.message_user(
            request,
            f"{updated} comprobante(s) rechazado(s). El cliente puede volver a subir.",
            level=messages.WARNING,
        )


@admin.register(PaymentSettings)
class PaymentSettingsAdmin(ModelAdmin):
    """Singleton: siempre una fila."""

    fieldsets = (
        ("Yape", {
            "fields": ("yape_enabled", "yape_holder_name", "yape_phone", "yape_qr", "yape_instructions"),
        }),
    )
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not PaymentSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = PaymentSettings.load()
        from django.shortcuts import redirect
        return redirect(f"../../orders/paymentsettings/{obj.pk}/change/")


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
