from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.mail import send_mail
from django.db.models import Count, Q, Sum
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import display
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import Customer, Role, User, WalletTransaction


JHELIZ_FIELDSETS_EXTRA = (
    ("Jheliz", {
        "fields": (
            "role", "phone", "telegram_username",
            "wallet_balance", "distributor_approved", "admin_notes",
        )
    }),
)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    list_display = (
        "username", "email", "role", "distributor_approved",
        "wallet_balance", "is_staff", "date_joined",
    )
    list_filter = ("role", "distributor_approved", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name", "phone", "telegram_username")
    actions = ["approve_distributor", "revoke_distributor"]

    fieldsets = BaseUserAdmin.fieldsets + JHELIZ_FIELDSETS_EXTRA
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Jheliz", {
            "fields": ("email", "role", "phone", "telegram_username"),
        }),
    )

    @admin.action(description="Aprobar como distribuidor")
    def approve_distributor(self, request, queryset):
        count = 0
        for user in queryset:
            if user.role != Role.DISTRIBUIDOR:
                user.role = Role.DISTRIBUIDOR
            user.distributor_approved = True
            user.save(update_fields=["role", "distributor_approved"])
            if user.email:
                try:
                    html = render_to_string("emails/distributor_approved.html", {"user": user})
                    send_mail(
                        subject="Tu cuenta de distribuidor Jheliz ha sido aprobada",
                        message=(
                            f"Hola {user.get_full_name() or user.username},\n\n"
                            "Tu solicitud de distribuidor fue aprobada. Ya puedes ver los precios mayoristas "
                            "entrando a https://jhelizservicestv.xyz/distribuidor/panel/"
                        ),
                        from_email=None,
                        recipient_list=[user.email],
                        html_message=html,
                        fail_silently=True,
                    )
                except Exception:
                    pass
            count += 1
        self.message_user(request, f"{count} usuarios aprobados como distribuidor.")

    @admin.action(description="Revocar aprobación de distribuidor")
    def revoke_distributor(self, request, queryset):
        count = queryset.update(distributor_approved=False)
        self.message_user(request, f"{count} distribuidores desaprobados.")


@admin.register(Customer)
class CustomerAdmin(ModelAdmin):
    """Vista de clientes con métricas agregadas y notas internas."""

    list_display = (
        "username", "display_full_name", "email", "phone_display",
        "orders_count", "spent_total", "last_order_at", "whatsapp_link",
    )
    list_filter = ("is_active", "date_joined")
    search_fields = ("username", "email", "first_name", "last_name", "phone", "telegram_username")
    readonly_fields = (
        "date_joined", "last_login", "orders_summary", "tickets_summary",
        "platforms_summary",
    )
    fieldsets = (
        ("Perfil", {
            "fields": (
                "username", "email", "first_name", "last_name",
                "phone", "telegram_username", "is_active",
            ),
        }),
        ("Notas internas", {
            "fields": ("admin_notes",),
            "description": "Sólo visible para el equipo.",
        }),
        ("Historial", {
            "fields": ("orders_summary", "tickets_summary", "platforms_summary"),
        }),
        ("Fechas", {
            "fields": ("date_joined", "last_login"),
            "classes": ("collapse",),
        }),
    )
    list_per_page = 50

    def get_queryset(self, request):
        qs = super().get_queryset(request).filter(role=Role.CLIENTE)
        qs = qs.annotate(
            _orders_count=Count("orders", distinct=True),
            _spent_total=Sum(
                "orders__total",
                filter=Q(orders__status__in=["paid", "preparing", "delivered"]),
            ),
        )
        return qs

    def save_model(self, request, obj, form, change):
        if not change:
            obj.role = Role.CLIENTE
        super().save_model(request, obj, form, change)

    @display(description="Nombre")
    def display_full_name(self, obj):
        return obj.get_full_name() or "—"

    @display(description="Teléfono / WhatsApp")
    def phone_display(self, obj):
        return obj.phone or "—"

    @display(description="# Pedidos", ordering="_orders_count")
    def orders_count(self, obj):
        return getattr(obj, "_orders_count", 0)

    @display(description="Total gastado", ordering="_spent_total")
    def spent_total(self, obj):
        return f"S/ {(getattr(obj, '_spent_total', None) or 0):,.2f}"

    @display(description="Último pedido")
    def last_order_at(self, obj):
        o = obj.orders.order_by("-created_at").first()
        return o.created_at.strftime("%d %b %Y") if o else "—"

    @display(description="WhatsApp")
    def whatsapp_link(self, obj):
        if not obj.phone:
            return "—"
        num = "".join(c for c in obj.phone if c.isdigit())
        if not num:
            return "—"
        return format_html(
            '<a href="https://wa.me/{0}" target="_blank" rel="noopener" '
            'class="text-green-500 hover:underline">WhatsApp</a>',
            num,
        )

    @admin.display(description="Pedidos")
    def orders_summary(self, obj):
        orders = obj.orders.order_by("-created_at")[:10]
        if not orders:
            return "—"
        rows = []
        for o in orders:
            url = reverse("admin:orders_order_change", args=[o.pk])
            rows.append(
                f'<tr>'
                f'<td><a href="{url}" style="color:#f472b6">#{o.short_uuid}</a></td>'
                f'<td>{o.created_at.strftime("%d %b %Y")}</td>'
                f'<td>{o.get_status_display()}</td>'
                f'<td>{o.currency} {o.total}</td>'
                f'</tr>'
            )
        table = (
            "<table style='width:100%;font-size:13px;border-collapse:collapse'>"
            "<thead><tr style='text-align:left;color:#94a3b8'>"
            "<th>#</th><th>Fecha</th><th>Estado</th><th>Total</th>"
            "</tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )
        return format_html(table)

    @admin.display(description="Tickets")
    def tickets_summary(self, obj):
        tickets = obj.tickets.order_by("-updated_at")[:8] if hasattr(obj, "tickets") else []
        if not tickets:
            return "—"
        rows = []
        for t in tickets:
            url = reverse("admin:support_ticket_change", args=[t.pk])
            rows.append(
                f'<li><a href="{url}" style="color:#f472b6">#{t.pk}</a> '
                f'— {t.subject} · <em>{t.get_status_display()}</em></li>'
            )
        return format_html("<ul style='margin:0;padding-left:18px'>" + "".join(rows) + "</ul>")

    @admin.display(description="Plataformas compradas")
    def platforms_summary(self, obj):
        rows = (
            obj.orders.filter(status__in=["paid", "preparing", "delivered"])
            .values("items__product_name")
            .annotate(qty=Count("items"))
            .order_by("-qty")[:8]
        )
        if not rows:
            return "—"
        chips = "".join(
            f"<span style='display:inline-block;margin:2px 4px 0 0;padding:2px 8px;"
            f"border-radius:12px;background:rgba(244,114,182,0.15);color:#f9a8d4;"
            f"font-size:12px;'>{r['items__product_name']} × {r['qty']}</span>"
            for r in rows if r["items__product_name"]
        )
        return format_html(chips or "—")


@admin.register(WalletTransaction)
class WalletTransactionAdmin(ModelAdmin):
    list_display = ("user", "kind", "amount", "balance_after", "reference", "created_at")
    list_filter = ("kind", "created_at")
    search_fields = ("user__username", "user__email", "reference")
    autocomplete_fields = ("user",)
    readonly_fields = ("balance_after", "created_at")
