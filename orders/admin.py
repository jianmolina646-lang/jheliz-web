from django import forms
from django.contrib import admin, messages
from django.db import models, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from import_export import resources
from import_export.admin import ExportMixin
from import_export.fields import Field
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.import_export.forms import ExportForm, ImportForm, SelectableFieldsExportForm
from unfold.decorators import display

from . import credentials as creds_utils
from . import emails
from .models import (
    Coupon, DistributorOrder, EmailLog, Order, OrderItem, PaymentSettings,
    ReminderRunLog,
)


class OrderResource(resources.ModelResource):
    """Resource for exporting Orders to CSV/XLSX from the admin."""

    customer_email = Field(attribute="email", column_name="email")
    customer_name = Field(column_name="cliente")
    short_id = Field(attribute="short_uuid", column_name="id_corto")
    items_summary = Field(column_name="items")
    subtotal = Field(attribute="subtotal", column_name="subtotal")
    discount = Field(attribute="discount_amount", column_name="descuento")
    coupon_used = Field(attribute="coupon_code", column_name="cupon")

    def dehydrate_customer_name(self, order):
        if order.user:
            full = (order.user.get_full_name() or order.user.username).strip()
            return full
        return order.email or "(invitado)"

    class Meta:
        model = Order
        fields = (
            "short_id", "customer_name", "customer_email", "phone",
            "status", "channel", "payment_provider", "payment_reference",
            "subtotal", "discount", "coupon_used", "total", "items_summary", "created_at",
        )
        export_order = fields

    def dehydrate_items_summary(self, order):
        return " | ".join(
            f"{i.product_name} \u2014 {i.plan_name} x{i.quantity}"
            for i in order.items.all()
        )


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


class DeliverCredentialsForm(forms.Form):
    """Formulario dinámico: un textarea por cada item del pedido.

    Para cada item, además del textarea de credenciales y la fecha de
    vencimiento, expone una lista de StockItems disponibles (mismo producto
    y compatible con el plan). El template los muestra como botones que,
    al hacer click, rellenan el textarea con las credenciales del stock
    elegido. Al guardar, ese StockItem queda marcado como vendido.
    """

    def __init__(self, *args, order: Order | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.order = order
        # Estructura amigable para el template: una lista de bloques, uno
        # por cada item del pedido, ya con BoundField objects listos para
        # renderizar.
        self.items_data: list[dict] = []
        if order is None:
            return
        from catalog.models import StockItem  # import diferido para evitar circulares

        for item in order.items.all():
            creds_name = f"creds_{item.pk}"
            expires_name = f"expires_{item.pk}"
            stock_name = f"stock_used_{item.pk}"
            self.fields[creds_name] = forms.CharField(
                label=f"{item.product_name} — {item.plan_name}",
                widget=forms.Textarea(attrs={
                    "rows": 4,
                    "id": f"id_{creds_name}",
                    "class": "w-full p-3 rounded border border-base-200 dark:border-base-800",
                    "style": "font-family:Menlo,Consolas,monospace;font-size:13px;"
                             "background:#0b0217;color:#f9a8d4;",
                    "placeholder": "email: ...\nclave: ...\nperfil: ...\nPIN: ...",
                }),
                initial=item.delivered_credentials,
                required=False,
            )
            self.fields[expires_name] = forms.DateTimeField(
                label="Vence (opcional)",
                required=False,
                widget=forms.DateTimeInput(attrs={
                    "type": "datetime-local",
                    "id": f"id_{expires_name}",
                    "class": "p-2 rounded border border-base-200 dark:border-base-800",
                }),
                initial=item.expires_at,
            )
            self.fields[stock_name] = forms.IntegerField(
                required=False,
                widget=forms.HiddenInput(attrs={"id": f"id_{stock_name}"}),
            )
            # Stocks disponibles para este item: mismo producto, plan
            # exacto o stock genérico (plan=None).
            stocks = list(
                StockItem.objects.filter(
                    product_id=item.product_id,
                    status=StockItem.Status.AVAILABLE,
                )
                .filter(models.Q(plan_id=item.plan_id) | models.Q(plan__isnull=True))
                .select_related("plan")
                .order_by("created_at")[:10]
            )
            self.items_data.append({
                "item": item,
                "stocks": stocks,
                "creds_field": self[creds_name],
                "expires_field": self[expires_name],
                "stock_field": self[stock_name],
                "creds_id": f"id_{creds_name}",
                "stock_id": f"id_{stock_name}",
            })


@admin.register(Order)
class OrderAdmin(ExportMixin, ModelAdmin):
    resource_classes = (OrderResource,)
    export_form_class = SelectableFieldsExportForm
    list_display = (
        "short_uuid", "display_customer", "display_status", "channel",
        "payment_provider", "total", "display_actions", "created_at",
    )
    list_display_links = ("short_uuid", "display_customer")
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
    actions = (
        "mark_preparing", "mark_delivered",
        "confirm_yape_payment", "reject_yape_payment",
        "resend_delivered_emails",
    )
    list_filter_submit = True
    compressed_fields = True
    list_select_related = ("user",)
    change_form_template = "admin/orders/order/change_form.html"

    def get_queryset(self, request):
        # Trae el FK user de un solo JOIN (display_customer lo usa).
        return super().get_queryset(request).select_related("user")

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

    # ---- Columnas decoradas -------------------------------------------------

    @display(description="Cliente")
    def display_customer(self, obj: Order):
        from urllib.parse import quote as _q
        name = (obj.user.get_full_name() if obj.user else "") or obj.email or obj.phone or "—"
        if obj.email:
            link = f"/jheliz-admin/customers/{_q(obj.email, safe='')}/"
            return format_html(
                '<div style="line-height:1.2">'
                '<div><a href="{}" title="Ver vista 360°" style="color:inherit;border-bottom:1px dotted #f472b6">{}</a></div>'
                '<div style="font-size:11px;color:#94a3b8">{}</div>'
                '</div>',
                link, name, obj.email,
            )
        return format_html(
            '<div style="line-height:1.2">'
            '<div>{}</div>'
            '<div style="font-size:11px;color:#94a3b8">{}</div>'
            '</div>',
            name,
            obj.email or "",
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

    @display(description="Acciones rápidas")
    def display_actions(self, obj: Order):
        buttons = []
        btn_style = (
            "display:inline-block;padding:3px 10px;margin:0 2px;border-radius:6px;"
            "font-size:11px;text-decoration:none;"
        )
        if obj.status == Order.Status.VERIFYING and obj.payment_provider == "yape":
            buttons.append(format_html(
                '<a href="{}" style="{}background:#22c55e;color:#fff">✓ Confirmar</a>',
                reverse("admin:orders_order_confirm_yape", args=[obj.pk]),
                btn_style,
            ))
            buttons.append(format_html(
                '<a href="{}" style="{}background:#ef4444;color:#fff">✕ Rechazar</a>',
                reverse("admin:orders_order_reject_yape", args=[obj.pk]),
                btn_style,
            ))
        if obj.status in {Order.Status.PAID, Order.Status.PREPARING, Order.Status.VERIFYING}:
            buttons.append(format_html(
                '<a href="{}" style="{}background:#f472b6;color:#fff">📦 Entregar</a>',
                reverse("admin:orders_order_deliver", args=[obj.pk]),
                btn_style,
            ))
        if obj.status == Order.Status.DELIVERED:
            buttons.append(format_html(
                '<a href="{}" style="{}background:#0ea5e9;color:#fff">↻ Reenviar</a>',
                reverse("admin:orders_order_resend", args=[obj.pk]),
                btn_style,
            ))
        if not buttons:
            return "—"
        return format_html("".join(str(b) for b in buttons))

    @admin.display(description="Comprobante")
    def payment_proof_preview(self, obj: Order):
        if not obj.payment_proof:
            return "—"
        return format_html(
            '<a href="{0}" target="_blank" rel="noopener">'
            '<img src="{0}" style="max-width:320px;max-height:420px;border-radius:8px;'
            'border:1px solid #334155" /></a>',
            obj.payment_proof.url,
        )

    # ---- URLs extra ---------------------------------------------------------

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "yape-inbox/",
                self.admin_site.admin_view(self.yape_inbox_view),
                name="orders_order_yape_inbox",
            ),
            path(
                "kanban/",
                self.admin_site.admin_view(self.kanban_view),
                name="orders_order_kanban",
            ),
            path(
                "<int:pk>/confirm-yape/",
                self.admin_site.admin_view(self.confirm_yape_view),
                name="orders_order_confirm_yape",
            ),
            path(
                "<int:pk>/reject-yape/",
                self.admin_site.admin_view(self.reject_yape_view),
                name="orders_order_reject_yape",
            ),
            path(
                "<int:pk>/deliver/",
                self.admin_site.admin_view(self.deliver_view),
                name="orders_order_deliver",
            ),
            path(
                "<int:pk>/resend/",
                self.admin_site.admin_view(self.resend_view),
                name="orders_order_resend",
            ),
        ]
        return custom + urls

    # ---- Bandeja de verificación Yape --------------------------------------

    def yape_inbox_view(self, request):
        """Pantalla dedicada para aprobar/rechazar comprobantes Yape de un vistazo.

        Lista solo los pedidos con comprobante subido y pendientes de
        verificación, con vista previa grande y acciones inline.
        """
        qs = (
            Order.objects.filter(
                status=Order.Status.VERIFYING,
                payment_provider="yape",
            )
            .exclude(payment_proof="")
            .select_related("user", "coupon")
            .prefetch_related("items")
            .order_by("-payment_proof_uploaded_at", "-created_at")
        )
        context = {
            **self.admin_site.each_context(request),
            "orders": qs,
            "title": "Bandeja de verificación Yape",
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
        }
        return TemplateResponse(request, "admin/orders/order/yape_inbox.html", context)

    # ---- Kanban ------------------------------------------------------------

    def kanban_view(self, request):
        """Tablero con columnas por estado — vista rápida del pipeline.

        Agrupa pedidos recientes en columnas por estado para ver de un
        vistazo cuántos hay en cada etapa y saltar al detalle.
        """
        from datetime import timedelta

        try:
            window_days = max(1, min(365, int(request.GET.get("days", 30))))
        except (ValueError, TypeError):
            window_days = 30
        since = timezone.now() - timedelta(days=window_days)

        qs = (
            Order.objects.filter(created_at__gte=since)
            .select_related("user")
            .prefetch_related("items")
            .order_by("-created_at")
        )
        columns_spec = [
            ("pending", "Pendiente de pago", [Order.Status.PENDING], "warning"),
            ("verifying", "Verificando", [Order.Status.VERIFYING], "orange"),
            ("preparing", "En preparación", [Order.Status.PAID, Order.Status.PREPARING], "info"),
            ("delivered", "Entregado", [Order.Status.DELIVERED], "success"),
            ("closed", "Cerrados", [Order.Status.CANCELED, Order.Status.FAILED, Order.Status.REFUNDED], "muted"),
        ]
        by_status: dict[str, list[Order]] = {}
        for order in qs:
            by_status.setdefault(order.status, []).append(order)
        columns = []
        for key, label, states, tone in columns_spec:
            orders = []
            for s in states:
                orders.extend(by_status.get(s, []))
            orders.sort(key=lambda o: o.created_at, reverse=True)
            columns.append({
                "key": key,
                "label": label,
                "tone": tone,
                "orders": orders[:50],  # cap por columna para no saturar
                "count": len(orders),
                "capped": len(orders) > 50,
            })
        context = {
            **self.admin_site.each_context(request),
            "columns": columns,
            "window_days": window_days,
            "title": "Kanban de pedidos",
            "opts": self.model._meta,
            "window_options": (7, 30, 60, 90, 180, 365),
        }
        return TemplateResponse(request, "admin/orders/order/kanban.html", context)

    # ---- Vistas 1-clic ------------------------------------------------------

    def _back(self, request, order):
        ref = request.META.get("HTTP_REFERER") or reverse(
            "admin:orders_order_change", args=[order.pk]
        )
        return HttpResponseRedirect(ref)

    def confirm_yape_view(self, request, pk: int):
        order = get_object_or_404(Order, pk=pk)
        if order.payment_provider != "yape" or not order.payment_proof:
            self.message_user(
                request,
                "Este pedido no tiene comprobante Yape para confirmar.",
                level=messages.WARNING,
            )
            return self._back(request, order)
        order.status = Order.Status.PREPARING
        order.paid_at = order.paid_at or timezone.now()
        order.payment_rejection_reason = ""
        order.save(update_fields=["status", "paid_at", "payment_rejection_reason"])
        from .auto_delivery import auto_deliver_distributor_order

        delivered, missing = auto_deliver_distributor_order(order)
        if delivered:
            self.message_user(
                request,
                f"Pago Yape confirmado y cuenta entregada autom\u00e1ticamente "
                f"al distribuidor de #{order.short_uuid}. Stock descontado.",
                level=messages.SUCCESS,
            )
            return redirect("admin:orders_order_changelist")
        emails.send_order_preparing(order)
        if missing:
            self.message_user(
                request,
                f"Pago Yape confirmado para #{order.short_uuid}, pero falta stock "
                f"para: {', '.join(missing)}. Carg\u00e1 stock o entreg\u00e1 manual.",
                level=messages.WARNING,
            )
        else:
            self.message_user(
                request,
                f"Pago Yape confirmado para #{order.short_uuid}. Se notific\u00f3 al cliente.",
                level=messages.SUCCESS,
            )
        return redirect("admin:orders_order_deliver", pk=order.pk)

    def reject_yape_view(self, request, pk: int):
        order = get_object_or_404(Order, pk=pk)
        if order.payment_provider != "yape":
            self.message_user(request, "Este pedido no es Yape.", level=messages.WARNING)
            return self._back(request, order)
        if request.method == "POST":
            reason = (request.POST.get("reason") or "").strip()
            if not reason:
                reason = (
                    "No pudimos verificar el comprobante. Por favor sube una captura "
                    "más clara donde se vea el monto y el destinatario."
                )
            order.status = Order.Status.PENDING
            order.payment_rejection_reason = reason
            order.save(update_fields=["status", "payment_rejection_reason"])
            emails.send_yape_proof_rejected(order)
            self.message_user(
                request,
                f"Comprobante Yape rechazado para #{order.short_uuid}. Se notificó al cliente.",
                level=messages.WARNING,
            )
            # Si el rechazo vino de la bandeja, volver a la bandeja.
            referer = request.META.get("HTTP_REFERER") or ""
            if "yape-inbox" in referer:
                return redirect("admin:orders_order_yape_inbox")
            return redirect("admin:orders_order_changelist")
        context = {
            **self.admin_site.each_context(request),
            "order": order,
            "opts": self.model._meta,
            "title": f"Rechazar comprobante Yape — #{order.short_uuid}",
        }
        return TemplateResponse(request, "admin/orders/order/reject_yape.html", context)

    def deliver_view(self, request, pk: int):
        order = get_object_or_404(Order, pk=pk)
        if request.method == "POST":
            form = DeliverCredentialsForm(request.POST, order=order)
            if form.is_valid():
                # Atomicidad: si algo falla a mitad, no queremos un pedido
                # con la mitad de las credenciales escritas y la otra mitad
                # vacía, y mucho menos con status=DELIVERED inconsistente.
                from catalog.models import StockItem  # import diferido

                with transaction.atomic():
                    for item in order.items.all():
                        item.delivered_credentials = form.cleaned_data.get(
                            f"creds_{item.pk}", ""
                        ) or item.delivered_credentials
                        expires = form.cleaned_data.get(f"expires_{item.pk}")
                        if expires:
                            item.expires_at = expires
                        # Si se usó un stock para auto-rellenar, marcarlo
                        # como vendido y vincularlo al item.
                        stock_id = form.cleaned_data.get(f"stock_used_{item.pk}")
                        if stock_id:
                            stock = (
                                StockItem.objects.select_for_update()
                                .filter(pk=stock_id, status=StockItem.Status.AVAILABLE)
                                .first()
                            )
                            if stock is not None:
                                stock.status = StockItem.Status.SOLD
                                stock.sold_at = timezone.now()
                                stock.save(update_fields=["status", "sold_at"])
                                item.stock_item = stock
                        item.save(update_fields=[
                            "delivered_credentials", "expires_at", "stock_item",
                        ])
                    order.status = Order.Status.DELIVERED
                    order.delivered_at = timezone.now()
                    order.paid_at = order.paid_at or order.delivered_at
                    order.save(update_fields=["status", "delivered_at", "paid_at"])
                # El email viaja DESPUÉS del commit (si la transacción aborta,
                # no enviamos un correo con datos que no quedaron guardados).
                transaction.on_commit(lambda: emails.send_order_delivered(order))
                self.message_user(
                    request,
                    f"Pedido #{order.short_uuid} entregado. Email con credenciales enviado.",
                    level=messages.SUCCESS,
                )
                return redirect("admin:orders_order_changelist")
        else:
            form = DeliverCredentialsForm(order=order)
        context = {
            **self.admin_site.each_context(request),
            "order": order,
            "form": form,
            "opts": self.model._meta,
            "title": f"Entregar credenciales — #{order.short_uuid}",
        }
        return TemplateResponse(request, "admin/orders/order/deliver.html", context)

    def resend_view(self, request, pk: int):
        order = get_object_or_404(Order, pk=pk)
        emails.send_order_delivered(order)
        self.message_user(
            request,
            f"Credenciales reenviadas al cliente de #{order.short_uuid}.",
            level=messages.SUCCESS,
        )
        return self._back(request, order)

    # ---- Bulk actions previas -----------------------------------------------

    @admin.action(description="Marcar como En preparación")
    def mark_preparing(self, request, queryset):
        from .auto_delivery import auto_deliver_distributor_order

        count = 0
        auto_delivered = 0
        for order in queryset:
            order.status = Order.Status.PREPARING
            order.save(update_fields=["status"])
            delivered, _missing = auto_deliver_distributor_order(order)
            if delivered:
                auto_delivered += 1
            count += 1
        msg = f"{count} pedidos marcados como en preparaci\u00f3n."
        if auto_delivered:
            msg += (
                f" {auto_delivered} de distribuidor entregado(s) "
                "autom\u00e1ticamente con stock descontado."
            )
        self.message_user(request, msg)

    @admin.action(description="Marcar como Entregado")
    def mark_delivered(self, request, queryset):
        count = 0
        for order in queryset:
            order.status = Order.Status.DELIVERED
            order.delivered_at = timezone.now()
            order.save(update_fields=["status", "delivered_at"])
            count += 1
        self.message_user(request, f"{count} pedidos marcados como entregados.")

    @admin.action(description="✅ Confirmar pago Yape → En preparación")
    def confirm_yape_payment(self, request, queryset):
        from .auto_delivery import auto_deliver_distributor_order

        now = timezone.now()
        updated = 0
        auto_delivered = 0
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
            delivered, _missing = auto_deliver_distributor_order(order)
            if delivered:
                auto_delivered += 1
            else:
                emails.send_order_preparing(order)
            updated += 1
        if updated:
            msg = f"{updated} pago(s) Yape confirmado(s). Se envi\u00f3 email al cliente."
            if auto_delivered:
                msg += (
                    f" {auto_delivered} pedido(s) de distribuidor entregado(s) "
                    "autom\u00e1ticamente con stock descontado."
                )
            self.message_user(request, msg, level=messages.SUCCESS)
        if skipped:
            self.message_user(
                request,
                f"{skipped} pedido(s) ignorado(s) (no son Yape o no tienen comprobante).",
                level=messages.WARNING,
            )

    @admin.action(description="❌ Rechazar comprobante Yape")
    def reject_yape_payment(self, request, queryset):
        updated = 0
        for order in queryset:
            if order.payment_provider != "yape":
                continue
            if not order.payment_rejection_reason:
                order.payment_rejection_reason = (
                    "No pudimos verificar el comprobante. Por favor sube una captura más clara "
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

    @admin.action(description="↻ Reenviar correo con credenciales (entregados)")
    def resend_delivered_emails(self, request, queryset):
        sent = 0
        skipped = 0
        for order in queryset:
            if order.status != Order.Status.DELIVERED:
                skipped += 1
                continue
            emails.send_order_delivered(order)
            sent += 1
        if sent:
            self.message_user(
                request,
                f"Reenviadas las credenciales a {sent} cliente(s).",
                level=messages.SUCCESS,
            )
        if skipped:
            self.message_user(
                request,
                f"{skipped} pedido(s) ignorado(s) por no estar en estado Entregado.",
                level=messages.WARNING,
            )


@admin.register(DistributorOrder)
class DistributorOrderAdmin(OrderAdmin):
    """Mismo OrderAdmin pero filtrado a pedidos de distribuidores aprobados."""

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(user__role="distribuidor", user__distributor_approved=True)


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
        return redirect(f"../../orders/paymentsettings/{obj.pk}/change/")


@admin.register(OrderItem)
class OrderItemAdmin(ModelAdmin):
    list_display = (
        "order", "product_name", "plan_name",
        "requested_profile_name", "requested_pin",
        "final_customer_name", "broken_badge",
        "unit_price", "quantity", "expires_at",
    )
    list_filter = ("product__category", "product", "reported_broken_at")
    search_fields = (
        "order__uuid", "product_name", "plan_name",
        "requested_profile_name", "requested_pin",
        "final_customer_name", "final_customer_whatsapp",
    )

    @admin.display(description="¿Caída?")
    def broken_badge(self, obj):
        if obj.reported_broken_at:
            return "🚨 Sí"
        return ""
    autocomplete_fields = ("order", "product", "plan", "stock_item")
    actions = ("action_replace_account", "action_rollback_replacement")

    # ------------------------------------------------------------------
    # Reemplazo seguro de cuenta
    # ------------------------------------------------------------------

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "replace-account/",
                self.admin_site.admin_view(self.replace_account_view),
                name="orders_orderitem_replace_account",
            ),
        ]
        return custom + urls

    @admin.action(description="Reemplazar cuenta (correo + contraseña)")
    def action_replace_account(self, request, queryset):
        # Restringe a items que ya tienen credenciales entregadas
        ids = list(queryset.values_list("pk", flat=True))
        if not ids:
            self.message_user(
                request, "Seleccioná al menos un item.", level=messages.WARNING,
            )
            return None
        url = reverse("admin:orders_orderitem_replace_account")
        qs = "&".join(f"ids={pk}" for pk in ids)
        return HttpResponseRedirect(f"{url}?{qs}")

    @admin.action(description="Deshacer último reemplazo de cuenta")
    def action_rollback_replacement(self, request, queryset):
        from datetime import timedelta

        rollback_window = timezone.now() - timedelta(days=30)
        done = 0
        skipped = 0
        with transaction.atomic():
            for item in queryset.select_for_update():
                if (
                    not item.previous_delivered_credentials
                    or item.credentials_replaced_at is None
                    or item.credentials_replaced_at < rollback_window
                ):
                    skipped += 1
                    continue
                item.delivered_credentials = item.previous_delivered_credentials
                item.previous_delivered_credentials = ""
                item.credentials_replaced_at = None
                item.save(update_fields=[
                    "delivered_credentials",
                    "previous_delivered_credentials",
                    "credentials_replaced_at",
                ])
                done += 1
        if done:
            self.message_user(
                request,
                f"{done} item(s) restaurado(s) a las credenciales anteriores.",
                level=messages.SUCCESS,
            )
        if skipped:
            self.message_user(
                request,
                f"{skipped} item(s) no tenían reemplazo reciente — no se tocaron.",
                level=messages.WARNING,
            )

    def replace_account_view(self, request):
        """Vista con preview + doble confirmación + ejecución atómica."""
        raw_ids = request.GET.getlist("ids") or request.POST.getlist("ids")
        try:
            ids = [int(x) for x in raw_ids if x]
        except ValueError:
            ids = []
        items = list(
            OrderItem.objects
            .filter(pk__in=ids)
            .select_related("order", "order__user", "product")
            .order_by("order__created_at")
        )
        # Enriquecer con info parseada y rol
        enriched = []
        for item in items:
            parsed = creds_utils.parse(item.delivered_credentials)
            user = item.order.user
            is_distributor = bool(user and getattr(user, "is_distributor", False))
            enriched.append({
                "item": item,
                "old_email": parsed.email,
                "old_password": parsed.password,
                "has_email": parsed.has_email_line,
                "has_password": parsed.has_password_line,
                "is_distributor": is_distributor,
                "role_label": "Distribuidor" if is_distributor else "Cliente",
            })

        error = ""
        if request.method == "POST" and request.POST.get("confirm") == "1":
            new_email = (request.POST.get("new_email") or "").strip()
            new_password = (request.POST.get("new_password") or "").strip()
            confirm_email = (request.POST.get("confirm_email") or "").strip()
            notify = request.POST.get("notify") == "on"
            selected = set(request.POST.getlist("apply"))

            if not new_email or not new_password:
                error = "Completá el nuevo correo y la nueva contraseña."
            elif confirm_email != new_email:
                error = "El correo de confirmación no coincide con el nuevo correo."
            else:
                updated = 0
                notified = 0
                now = timezone.now()
                with transaction.atomic():
                    for entry in enriched:
                        item = entry["item"]
                        if str(item.pk) not in selected:
                            continue
                        if not item.delivered_credentials:
                            continue
                        new_text = creds_utils.replace_account(
                            item.delivered_credentials, new_email, new_password,
                        )
                        item.previous_delivered_credentials = item.delivered_credentials
                        item.delivered_credentials = new_text
                        item.credentials_replaced_at = now
                        item.save(update_fields=[
                            "delivered_credentials",
                            "previous_delivered_credentials",
                            "credentials_replaced_at",
                        ])
                        updated += 1
                        if notify:
                            transaction.on_commit(
                                lambda it=item, d=entry["is_distributor"]:
                                emails.send_account_credentials_updated(
                                    it, is_distributor=d,
                                )
                            )
                            notified += 1
                self.message_user(
                    request,
                    f"{updated} item(s) con credenciales actualizadas."
                    + (f" {notified} email(s) enviado(s)." if notify else ""),
                    level=messages.SUCCESS,
                )
                return redirect("admin:orders_orderitem_changelist")

        context = {
            **self.admin_site.each_context(request),
            "title": "Reemplazar cuenta (correo + contraseña)",
            "opts": self.model._meta,
            "entries": enriched,
            "ids": ids,
            "error": error,
            "posted": request.method == "POST" and request.POST.get("confirm") == "1",
            "form_values": {
                "new_email": request.POST.get("new_email", "") if request.method == "POST" else "",
                "new_password": request.POST.get("new_password", "") if request.method == "POST" else "",
            },
        }
        return TemplateResponse(
            request,
            "admin/orders/orderitem/replace_account.html",
            context,
        )


@admin.register(Coupon)
class CouponAdmin(ModelAdmin):
    list_display = (
        "code", "discount_label_col", "audience", "is_active",
        "times_used", "max_uses", "valid_until", "min_order_total",
    )
    list_filter = ("is_active", "discount_type", "audience")
    search_fields = ("code", "description")
    list_editable = ("is_active",)
    readonly_fields = ("times_used", "created_at", "updated_at")
    fieldsets = (
        ("Cupón", {
            "fields": ("code", "description", "is_active"),
        }),
        ("Descuento", {
            "fields": ("discount_type", "discount_value", "min_order_total"),
        }),
        ("Disponibilidad", {
            "fields": ("audience", "valid_from", "valid_until"),
        }),
        ("Límites de uso", {
            "fields": ("max_uses", "max_uses_per_user", "times_used"),
        }),
        ("Auditoría", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
    actions = ("duplicate_coupon", "deactivate_coupons", "activate_coupons")

    @display(description="Descuento")
    def discount_label_col(self, obj):
        return obj.discount_label

    @admin.action(description="Duplicar cupón (copia con código '_COPY')")
    def duplicate_coupon(self, request, queryset):
        n = 0
        for coupon in queryset:
            base_code = f"{coupon.code}_COPY"
            new_code = base_code
            i = 2
            while Coupon.objects.filter(code=new_code).exists():
                new_code = f"{base_code}{i}"
                i += 1
            coupon.pk = None
            coupon.code = new_code
            coupon.times_used = 0
            coupon.is_active = False
            coupon.save()
            n += 1
        self.message_user(request, f"{n} cupón(es) duplicados (inactivos por defecto).")

    @admin.action(description="Desactivar")
    def deactivate_coupons(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} cupón(es) desactivados.")

    @admin.action(description="Activar")
    def activate_coupons(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} cupón(es) activados.")


@admin.register(EmailLog)
class EmailLogAdmin(ModelAdmin):
    """Auditoría de emails transaccionales enviados."""

    list_display = ("sent_at", "kind", "to_email", "subject", "display_status", "order")
    list_filter = ("kind", "status", "sent_at")
    search_fields = ("to_email", "subject", "order__uuid")
    autocomplete_fields = ("order",)
    readonly_fields = ("kind", "status", "to_email", "subject", "order", "error", "sent_at")
    date_hierarchy = "sent_at"
    list_filter_submit = True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Solo lectura — los logs no se editan, solo se consultan.
        return False

    @display(
        description="Estado",
        ordering="status",
        label={
            EmailLog.Status.SENT: "success",
            EmailLog.Status.FAILED: "danger",
        },
    )
    def display_status(self, obj: EmailLog):
        return obj.status, obj.get_status_display()


@admin.register(ReminderRunLog)
class ReminderRunLogAdmin(ModelAdmin):
    """Historial de runs del comando ``send_expiry_reminders``.

    Solo lectura: el cron es quien crea estos logs.
    """

    list_display = (
        "started_at", "display_total", "customer_count", "distri_count",
        "display_dry_run", "display_status",
    )
    list_filter = ("dry_run", "started_at")
    readonly_fields = (
        "started_at", "finished_at", "dry_run",
        "customer_count", "distri_count", "by_window", "error",
    )
    date_hierarchy = "started_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @display(description="Total", ordering="customer_count")
    def display_total(self, obj: ReminderRunLog) -> str:
        return str(obj.total)

    @display(description="Dry-run", boolean=True, ordering="dry_run")
    def display_dry_run(self, obj: ReminderRunLog) -> bool:
        return obj.dry_run

    @display(
        description="Estado",
        label={"ok": "success", "fail": "danger"},
    )
    def display_status(self, obj: ReminderRunLog):
        if obj.error:
            return "fail", "Falló"
        return "ok", "Ok"
