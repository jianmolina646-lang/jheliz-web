from decimal import Decimal

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.mail import send_mail
from django.db.models import Count, Max, Q, Sum
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import display
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .admin_helpers import (
    avatar_html,
    chip,
    chips,
    contact_actions,
    modern_table,
    stat_grid,
    time_ago,
    user_card_cell,
)
from .models import Customer, Distributor, Role, User, WalletTransaction


JHELIZ_FIELDSETS_EXTRA = (
    ("Jheliz", {
        "fields": (
            "role", "phone", "telegram_username",
            "wallet_balance", "distributor_approved", "admin_notes",
        )
    }),
)


# ---------------------------------------------------------------------------
# Helpers privados (cálculos compartidos entre Cliente y Distribuidor)
# ---------------------------------------------------------------------------

_PAID_STATUSES = ("paid", "preparing", "delivered")


def _orders_count(obj) -> int:
    return getattr(obj, "_orders_count", 0) or 0


def _spent_total(obj) -> Decimal:
    val = getattr(obj, "_spent_total", None)
    return Decimal(val or 0)


def _last_order_at(obj):
    return getattr(obj, "_last_order_at", None)


def _avg_ticket(obj) -> Decimal:
    n = _orders_count(obj)
    if not n:
        return Decimal("0")
    return _spent_total(obj) / n


def _customer_status_chip(obj):
    """Chip dinámico según comportamiento del cliente.

    - VIP: 5+ pedidos pagados o S/ 200+ gastados
    - RECURRENTE: 2-4 pedidos
    - NUEVO: 1 pedido
    - SIN COMPRAS: 0
    """
    n = _orders_count(obj)
    spent = _spent_total(obj)
    if n >= 5 or spent >= Decimal("200"):
        return chip("VIP", tone="pink", icon="diamond")
    if n >= 2:
        return chip("Recurrente", tone="info", icon="autorenew")
    if n == 1:
        return chip("Nuevo", tone="success", icon="bolt")
    return chip("Sin compras", tone="neutral", icon="hourglass_empty")


def _distrib_status_chip(obj):
    """Chip dinámico según estado y volumen del distribuidor."""
    if not obj.distributor_approved:
        return chip("Pendiente", tone="warning", icon="pending")
    n = _orders_count(obj)
    spent = _spent_total(obj)
    if n >= 10 or spent >= Decimal("500"):
        return chip("Top", tone="pink", icon="workspace_premium")
    if n >= 3:
        return chip("Activo", tone="success", icon="check_circle")
    return chip("Aprobado", tone="info", icon="verified")


# ---------------------------------------------------------------------------
# Staff (User) — UserAdmin con avatar + chips de rol
# ---------------------------------------------------------------------------

@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    list_display = (
        "user_card", "role_chip", "permission_chips",
        "wallet_balance", "last_seen", "actions_cell",
    )
    list_filter = ("role", "distributor_approved", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name", "phone", "telegram_username")
    actions = ["approve_distributor", "revoke_distributor"]
    list_per_page = 50

    fieldsets = BaseUserAdmin.fieldsets + JHELIZ_FIELDSETS_EXTRA
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Jheliz", {
            "fields": ("email", "role", "phone", "telegram_username"),
        }),
    )

    @display(description="Usuario")
    def user_card(self, obj):
        return user_card_cell(obj, sub=obj.email or obj.username)

    @display(description="Rol")
    def role_chip(self, obj):
        tone_map = {
            Role.ADMIN: ("pink", "shield_person"),
            Role.DISTRIBUIDOR: ("violet", "store"),
            Role.CLIENTE: ("info", "person"),
        }
        tone, icon = tone_map.get(obj.role, ("neutral", "person"))
        return chip(obj.get_role_display(), tone=tone, icon=icon)

    @display(description="Permisos")
    def permission_chips(self, obj):
        items = []
        if obj.is_superuser:
            items.append(("Superuser", "pink"))
        if obj.is_staff:
            items.append(("Staff", "violet"))
        if not obj.is_active:
            items.append(("Inactivo", "danger"))
        if obj.distributor_approved and obj.role == Role.DISTRIBUIDOR:
            items.append(("Distrib. aprobado", "success"))
        if not items:
            return format_html('<span class="jh-muted">—</span>')
        return chips(items)

    @display(description="Última conexión", ordering="last_login")
    def last_seen(self, obj):
        if not obj.last_login:
            return format_html('<span class="jh-muted">nunca</span>')
        return time_ago(obj.last_login)

    @display(description="Contacto")
    def actions_cell(self, obj):
        return contact_actions(obj)

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


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------

@admin.register(Customer)
class CustomerAdmin(ModelAdmin):
    """Vista de clientes con métricas agregadas y notas internas."""

    list_display = (
        "user_card", "status_chip",
        "orders_count", "spent_total", "last_order_at_relative",
        "actions_cell",
    )
    list_filter = ("is_active", "date_joined")
    search_fields = ("username", "email", "first_name", "last_name", "phone", "telegram_username")
    readonly_fields = (
        "date_joined", "last_login",
        "stats_panel", "orders_summary", "tickets_summary", "platforms_summary",
    )
    fieldsets = (
        ("Resumen", {
            "fields": ("stats_panel",),
            "description": "Foto rápida del cliente: pedidos, gasto y actividad reciente.",
        }),
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
        return qs.annotate(
            _orders_count=Count("orders", distinct=True),
            _spent_total=Sum(
                "orders__total",
                filter=Q(orders__status__in=_PAID_STATUSES),
            ),
            _last_order_at=Max("orders__created_at"),
        )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.role = Role.CLIENTE
        super().save_model(request, obj, form, change)

    # -- columnas listado ---------------------------------------------------
    @display(description="Cliente")
    def user_card(self, obj):
        sub = obj.email or (obj.phone or "—")
        return user_card_cell(obj, sub=sub)

    @display(description="Estado")
    def status_chip(self, obj):
        return _customer_status_chip(obj)

    @display(description="# Pedidos", ordering="_orders_count")
    def orders_count(self, obj):
        return _orders_count(obj)

    @display(description="Total gastado", ordering="_spent_total")
    def spent_total(self, obj):
        return f"S/ {_spent_total(obj):,.2f}"

    @display(description="Última actividad", ordering="_last_order_at")
    def last_order_at_relative(self, obj):
        ts = _last_order_at(obj)
        if not ts:
            return format_html('<span class="jh-muted">sin pedidos</span>')
        return time_ago(ts)

    @display(description="Contacto")
    def actions_cell(self, obj):
        return contact_actions(obj)

    # -- ficha (change_form) ------------------------------------------------
    @admin.display(description="")
    def stats_panel(self, obj):
        last = _last_order_at(obj)
        recent = "—"
        if last:
            recent = time_ago(last)
        cards = [
            {"label": "Pedidos", "value": str(_orders_count(obj)),
             "sub": "todos los estados", "tone": "cyan", "icon": "receipt_long"},
            {"label": "Total gastado", "value": f"S/ {_spent_total(obj):,.2f}",
             "sub": "pagados / entregados", "tone": "emerald", "icon": "payments"},
            {"label": "Ticket promedio", "value": f"S/ {_avg_ticket(obj):,.2f}",
             "sub": "por pedido", "tone": "violet", "icon": "trending_up"},
            {"label": "Última compra", "value": recent,
             "sub": last.strftime("%d %b %Y") if last else "—",
             "tone": "pink", "icon": "schedule"},
        ]
        status = _customer_status_chip(obj)
        actions = contact_actions(obj)
        head = format_html(
            '<div style="display:flex;align-items:center;gap:14px;margin-bottom:14px;flex-wrap:wrap">'
            '{avatar}'
            '<div style="flex:1;min-width:0">'
            '  <div style="font-weight:700;color:#fff;font-size:16px">{name}</div>'
            '  <div style="font-size:12.5px;color:#94a3b8">{email}</div>'
            '</div>'
            '{status}{actions}'
            '</div>',
            avatar=avatar_html(obj, size=48),
            name=obj.get_full_name() or obj.username,
            email=obj.email or "—",
            status=status,
            actions=actions,
        )
        return format_html("{}{}", head, stat_grid(cards))

    @admin.display(description="Pedidos recientes")
    def orders_summary(self, obj):
        orders = obj.orders.order_by("-created_at")[:10]
        rows = []
        for o in orders:
            url = reverse("admin:orders_order_change", args=[o.pk])
            rows.append([
                format_html('<a href="{}">#{}</a>', url, o.short_uuid),
                o.created_at.strftime("%d %b %Y"),
                chip(o.get_status_display(), tone=_order_tone(o.status)),
                f"{o.currency} {o.total}",
            ])
        return modern_table(["#", "Fecha", "Estado", "Total"], rows)

    @admin.display(description="Tickets")
    def tickets_summary(self, obj):
        if not hasattr(obj, "tickets"):
            return modern_table(["Asunto", "Estado", "Actualizado"], [])
        tickets = obj.tickets.order_by("-updated_at")[:8]
        rows = []
        for t in tickets:
            url = reverse("admin:support_ticket_change", args=[t.pk])
            rows.append([
                format_html('<a href="{}">#{} {}</a>', url, t.pk, t.subject),
                chip(t.get_status_display(), tone=_ticket_tone(t.status)),
                time_ago(t.updated_at),
            ])
        return modern_table(["Asunto", "Estado", "Actualizado"], rows)

    @admin.display(description="Plataformas compradas")
    def platforms_summary(self, obj):
        rows = (
            obj.orders.filter(status__in=_PAID_STATUSES)
            .values("items__product_name")
            .annotate(qty=Count("items"))
            .order_by("-qty")[:8]
        )
        items = [
            (f"{r['items__product_name']} × {r['qty']}", "pink")
            for r in rows if r["items__product_name"]
        ]
        if not items:
            return format_html('<div class="jh-empty">Aún no compró nada.</div>')
        return chips(items)


# ---------------------------------------------------------------------------
# Distribuidor
# ---------------------------------------------------------------------------

@admin.register(Distributor)
class DistributorAdmin(ModelAdmin):
    """Vista enfocada en distribuidores: estado, métricas, historial y notas."""

    list_display = (
        "user_card", "status_chip",
        "orders_count", "spent_total", "wallet_chip",
        "last_order_at_relative", "actions_cell",
    )
    list_filter = ("distributor_approved", "is_active", "date_joined")
    search_fields = (
        "username", "email", "first_name", "last_name",
        "phone", "telegram_username",
    )
    actions = ["approve_distributor", "revoke_distributor"]
    readonly_fields = (
        "date_joined", "last_login", "wallet_balance",
        "stats_panel", "orders_summary", "platforms_summary",
        "wallet_summary", "tickets_summary",
    )
    fieldsets = (
        ("Resumen", {
            "fields": ("stats_panel",),
            "description": "Estado del distribuidor de un vistazo.",
        }),
        ("Perfil", {
            "fields": (
                "username", "email", "first_name", "last_name",
                "phone", "telegram_username", "is_active",
            ),
        }),
        ("Estado distribuidor", {
            "fields": ("distributor_approved", "wallet_balance"),
            "description": "Aprueba para que vea precios mayoristas en /distribuidor/panel/.",
        }),
        ("Notas internas", {
            "fields": ("admin_notes",),
            "description": "Sólo visible para el equipo.",
        }),
        ("Historial", {
            "fields": (
                "orders_summary", "platforms_summary",
                "wallet_summary", "tickets_summary",
            ),
        }),
        ("Fechas", {
            "fields": ("date_joined", "last_login"),
            "classes": ("collapse",),
        }),
    )
    list_per_page = 50

    def get_queryset(self, request):
        qs = super().get_queryset(request).filter(role=Role.DISTRIBUIDOR)
        return qs.annotate(
            _orders_count=Count("orders", distinct=True),
            _spent_total=Sum(
                "orders__total",
                filter=Q(orders__status__in=_PAID_STATUSES),
            ),
            _last_order_at=Max("orders__created_at"),
        )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.role = Role.DISTRIBUIDOR
        super().save_model(request, obj, form, change)

    # -- columnas listado ---------------------------------------------------
    @display(description="Distribuidor")
    def user_card(self, obj):
        return user_card_cell(obj, sub=obj.email or obj.phone or "—")

    @display(description="Estado")
    def status_chip(self, obj):
        return _distrib_status_chip(obj)

    @display(description="# Pedidos", ordering="_orders_count")
    def orders_count(self, obj):
        return _orders_count(obj)

    @display(description="Total comprado", ordering="_spent_total")
    def spent_total(self, obj):
        return f"S/ {_spent_total(obj):,.2f}"

    @display(description="Saldo")
    def wallet_chip(self, obj):
        bal = Decimal(obj.wallet_balance or 0)
        if bal > 0:
            return chip(f"S/ {bal:,.2f}", tone="success", icon="account_balance_wallet")
        if bal < 0:
            return chip(f"S/ {bal:,.2f}", tone="danger", icon="account_balance_wallet")
        return chip("S/ 0.00", tone="neutral", icon="account_balance_wallet")

    @display(description="Última actividad", ordering="_last_order_at")
    def last_order_at_relative(self, obj):
        ts = _last_order_at(obj)
        if not ts:
            return format_html('<span class="jh-muted">sin pedidos</span>')
        return time_ago(ts)

    @display(description="Contacto")
    def actions_cell(self, obj):
        return contact_actions(obj)

    # -- ficha (change_form) ------------------------------------------------
    @admin.display(description="")
    def stats_panel(self, obj):
        last = _last_order_at(obj)
        cards = [
            {"label": "Pedidos", "value": str(_orders_count(obj)),
             "sub": "como distribuidor", "tone": "cyan", "icon": "receipt_long"},
            {"label": "Total comprado", "value": f"S/ {_spent_total(obj):,.2f}",
             "sub": "precios mayoristas", "tone": "emerald", "icon": "payments"},
            {"label": "Saldo wallet", "value": f"S/ {Decimal(obj.wallet_balance or 0):,.2f}",
             "sub": "disponible para gastar", "tone": "violet",
             "icon": "account_balance_wallet"},
            {"label": "Última compra", "value": time_ago(last) if last else "—",
             "sub": last.strftime("%d %b %Y") if last else "—",
             "tone": "pink", "icon": "schedule"},
        ]
        status = _distrib_status_chip(obj)
        approval = chip(
            "Aprobado" if obj.distributor_approved else "Pendiente",
            tone="success" if obj.distributor_approved else "warning",
            icon="verified_user" if obj.distributor_approved else "lock_clock",
        )
        actions = contact_actions(obj)
        head = format_html(
            '<div style="display:flex;align-items:center;gap:14px;margin-bottom:14px;flex-wrap:wrap">'
            '{avatar}'
            '<div style="flex:1;min-width:0">'
            '  <div style="font-weight:700;color:#fff;font-size:16px">{name}</div>'
            '  <div style="font-size:12.5px;color:#94a3b8">{email}</div>'
            '</div>'
            '<div style="display:flex;gap:6px;flex-wrap:wrap">{status}{approval}</div>'
            '{actions}'
            '</div>',
            avatar=avatar_html(obj, size=48),
            name=obj.get_full_name() or obj.username,
            email=obj.email or "—",
            status=status,
            approval=approval,
            actions=actions,
        )
        return format_html("{}{}", head, stat_grid(cards))

    @admin.display(description="Pedidos recientes")
    def orders_summary(self, obj):
        orders = obj.orders.order_by("-created_at")[:10]
        rows = []
        for o in orders:
            url = reverse("admin:orders_order_change", args=[o.pk])
            rows.append([
                format_html('<a href="{}">#{}</a>', url, o.short_uuid),
                o.created_at.strftime("%d %b %Y"),
                chip(o.get_status_display(), tone=_order_tone(o.status)),
                f"{o.currency} {o.total}",
            ])
        return modern_table(["#", "Fecha", "Estado", "Total"], rows)

    @admin.display(description="Plataformas compradas")
    def platforms_summary(self, obj):
        rows = (
            obj.orders.filter(status__in=_PAID_STATUSES)
            .values("items__product_name")
            .annotate(qty=Count("items"))
            .order_by("-qty")[:8]
        )
        items = [
            (f"{r['items__product_name']} × {r['qty']}", "violet")
            for r in rows if r["items__product_name"]
        ]
        if not items:
            return format_html('<div class="jh-empty">Aún no compró ninguna cuenta.</div>')
        return chips(items)

    @admin.display(description="Movimientos de saldo")
    def wallet_summary(self, obj):
        if not hasattr(obj, "wallet_transactions"):
            return modern_table(["Fecha", "Tipo", "Monto", "Saldo después", "Ref."], [])
        txs = obj.wallet_transactions.order_by("-created_at")[:8]
        rows = []
        for t in txs:
            sign = "+" if t.amount >= 0 else ""
            tone = "success" if t.amount >= 0 else "danger"
            rows.append([
                t.created_at.strftime("%d %b %Y"),
                t.get_kind_display(),
                chip(f"{sign}S/ {t.amount}", tone=tone),
                f"S/ {t.balance_after}",
                t.reference or "—",
            ])
        return modern_table(["Fecha", "Tipo", "Monto", "Saldo después", "Ref."], rows)

    @admin.display(description="Tickets")
    def tickets_summary(self, obj):
        if not hasattr(obj, "tickets"):
            return modern_table(["Asunto", "Estado", "Actualizado"], [])
        tickets = obj.tickets.order_by("-updated_at")[:8]
        rows = []
        for t in tickets:
            url = reverse("admin:support_ticket_change", args=[t.pk])
            rows.append([
                format_html('<a href="{}">#{} {}</a>', url, t.pk, t.subject),
                chip(t.get_status_display(), tone=_ticket_tone(t.status)),
                time_ago(t.updated_at),
            ])
        return modern_table(["Asunto", "Estado", "Actualizado"], rows)

    @admin.action(description="Aprobar distribuidor (envía email)")
    def approve_distributor(self, request, queryset):
        count = 0
        for user in queryset:
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
        self.message_user(request, f"{count} distribuidor(es) aprobado(s).")

    @admin.action(description="Revocar aprobación de distribuidor")
    def revoke_distributor(self, request, queryset):
        count = queryset.update(distributor_approved=False)
        self.message_user(request, f"{count} distribuidor(es) desaprobado(s).")


# ---------------------------------------------------------------------------
# Wallet
# ---------------------------------------------------------------------------

@admin.register(WalletTransaction)
class WalletTransactionAdmin(ModelAdmin):
    list_display = (
        "user_cell", "kind_chip", "amount_cell", "balance_after",
        "reference", "created_relative",
    )
    list_filter = ("kind", "created_at")
    search_fields = ("user__username", "user__email", "reference")
    autocomplete_fields = ("user",)
    readonly_fields = ("balance_after", "created_at")
    list_select_related = ("user",)

    @display(description="Usuario", ordering="user__email")
    def user_cell(self, obj):
        return user_card_cell(obj.user, sub=obj.user.email or obj.user.username)

    @display(description="Tipo", ordering="kind")
    def kind_chip(self, obj):
        tones = {
            "recarga":   ("success", "add_circle"),
            "compra":    ("info", "shopping_cart"),
            "reembolso": ("warning", "undo"),
            "ajuste":    ("violet", "tune"),
        }
        tone, icon = tones.get(obj.kind, ("neutral", "swap_horiz"))
        return chip(obj.get_kind_display(), tone=tone, icon=icon)

    @display(description="Monto", ordering="amount")
    def amount_cell(self, obj):
        positive = obj.kind in {"recarga", "reembolso"} or obj.amount >= 0
        sign = "+" if positive else "−"
        cls = "jh-amount jh-amount--pos" if positive else "jh-amount jh-amount--neg"
        return format_html(
            '<span class="{}">{} S/ {}</span>',
            cls, sign, f"{abs(obj.amount):,.2f}",
        )

    @display(description="Cuándo", ordering="-created_at")
    def created_relative(self, obj):
        return time_ago(obj.created_at)


# ---------------------------------------------------------------------------
# Mapeo de estados de Order/Ticket a tono de chip
# ---------------------------------------------------------------------------

def _order_tone(status: str) -> str:
    return {
        "delivered": "success",
        "paid": "info",
        "preparing": "violet",
        "pending": "warning",
        "verifying": "warning",
        "cancelled": "danger",
        "rejected": "danger",
        "refunded": "neutral",
    }.get(status, "neutral")


def _ticket_tone(status: str) -> str:
    return {
        "open": "warning",
        "in_progress": "info",
        "answered": "violet",
        "resolved": "success",
        "closed": "neutral",
    }.get(status, "neutral")
