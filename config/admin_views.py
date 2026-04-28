"""Vistas auxiliares del panel admin: reportes, clientes valiosos, health check
y endpoint de notificaciones para polling.

Se montan bajo `/jheliz-admin/...` antes del catch-all `admin.site.urls` para
que Django las matchee primero.
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import connection, transaction
from django.db.models import Count, Max, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST


def _admin_context(request, **extra):
    """Contexto base para que las vistas hereden de admin/base.html."""
    from django.contrib import admin

    ctx = {
        **admin.site.each_context(request),
        **extra,
    }
    return ctx


# ---------------------------------------------------------------------------
# Reports financieros + CSV export (#5)
# ---------------------------------------------------------------------------

@staff_member_required
def reports_view(request):
    """Reportes de ventas: hoy, 7d, 30d + top productos + ingreso por método."""
    from orders.models import Order, OrderItem

    today = timezone.localdate()
    paid_statuses = (
        Order.Status.PAID, Order.Status.PREPARING, Order.Status.DELIVERED,
    )
    paid_qs = Order.objects.filter(status__in=paid_statuses)

    def _range(days):
        start = timezone.now() - timedelta(days=days)
        agg = paid_qs.filter(paid_at__gte=start).aggregate(
            count=Count("id"), revenue=Sum("total"),
        )
        return {
            "count": agg["count"] or 0,
            "revenue": agg["revenue"] or Decimal("0"),
        }

    today_start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    today_stats_agg = paid_qs.filter(paid_at__gte=today_start).aggregate(
        count=Count("id"), revenue=Sum("total"),
    )
    today_stats = {
        "count": today_stats_agg["count"] or 0,
        "revenue": today_stats_agg["revenue"] or Decimal("0"),
    }
    week_stats = _range(7)
    month_stats = _range(30)
    year_stats = _range(365)

    # Top productos por revenue (últimos 30 días)
    last_30 = timezone.now() - timedelta(days=30)
    from django.db.models import F

    top_products = (
        OrderItem.objects
        .filter(order__status__in=paid_statuses, order__paid_at__gte=last_30)
        .values("product_name")
        .annotate(
            units=Sum("quantity"),
            revenue=Sum(F("unit_price") * F("quantity")),
        )
        .order_by("-revenue")[:10]
    )

    # Ingresos por método de pago (últimos 30 días)
    by_method = (
        paid_qs.filter(paid_at__gte=last_30)
        .values("payment_provider")
        .annotate(count=Count("id"), revenue=Sum("total"))
        .order_by("-revenue")
    )

    ctx = _admin_context(
        request,
        title="Reportes financieros",
        today_stats=today_stats,
        week_stats=week_stats,
        month_stats=month_stats,
        year_stats=year_stats,
        top_products=list(top_products),
        by_method=list(by_method),
        currency_symbol=settings.DEFAULT_CURRENCY_SYMBOL,
    )
    return render(request, "admin/reports.html", ctx)


@staff_member_required
def reports_export_csv(request):
    """Exporta los pedidos de un rango (default 30d) a CSV para el contador."""
    from orders.models import Order

    days = int(request.GET.get("days", 30))
    days = max(1, min(days, 365))
    start = timezone.now() - timedelta(days=days)

    qs = (
        Order.objects
        .filter(status__in=(
            Order.Status.PAID, Order.Status.PREPARING, Order.Status.DELIVERED,
        ))
        .filter(paid_at__gte=start)
        .order_by("-paid_at")
        .select_related("user")
    )

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    fname = f"pedidos_{timezone.localdate().isoformat()}_ultimos_{days}d.csv"
    response["Content-Disposition"] = f'attachment; filename="{fname}"'
    response.write("\ufeff")  # BOM para Excel
    writer = csv.writer(response)
    writer.writerow([
        "uuid", "fecha_pago", "estado", "metodo_pago", "referencia",
        "email", "telefono", "cliente", "total", "moneda",
    ])
    for o in qs.iterator():
        writer.writerow([
            str(o.uuid),
            o.paid_at.strftime("%Y-%m-%d %H:%M") if o.paid_at else "",
            o.get_status_display(),
            o.get_payment_provider_display() if hasattr(o, "get_payment_provider_display") else (o.payment_provider or ""),
            o.payment_reference or "",
            o.email or "",
            o.phone or "",
            (o.user.get_full_name() if o.user else "") or (o.user.username if o.user else ""),
            f"{o.total:.2f}" if o.total else "0.00",
            o.currency,
        ])
    return response


# ---------------------------------------------------------------------------
# Top customers / Clientes valiosos (#9)
# ---------------------------------------------------------------------------

@staff_member_required
def top_customers_view(request):
    from accounts.models import User
    from orders.models import Order

    paid_statuses = (
        Order.Status.PAID, Order.Status.PREPARING, Order.Status.DELIVERED,
    )

    from django.db.models import Q

    customers = (
        User.objects.annotate(
            orders_count=Count(
                "orders", filter=Q(orders__status__in=paid_statuses), distinct=True,
            ),
            total_spent=Sum(
                "orders__total", filter=Q(orders__status__in=paid_statuses),
            ),
            last_order_at=Max(
                "orders__paid_at", filter=Q(orders__status__in=paid_statuses),
            ),
        )
        .filter(orders_count__gt=0)
        .order_by("-total_spent")[:50]
    )

    ctx = _admin_context(
        request,
        title="Clientes valiosos",
        customers=list(customers),
        currency_symbol=settings.DEFAULT_CURRENCY_SYMBOL,
    )
    return render(request, "admin/top_customers.html", ctx)


# ---------------------------------------------------------------------------
# Health check de servicios externos (#17)
# ---------------------------------------------------------------------------

def _check_db():
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True, "OK"
    except Exception as exc:
        return False, str(exc)[:200]


def _check_smtp():
    backend = settings.EMAIL_BACKEND or ""
    if "console" in backend or "locmem" in backend or "dummy" in backend:
        return None, f"backend de desarrollo ({backend.split('.')[-1]})"
    host = getattr(settings, "EMAIL_HOST", "")
    port = getattr(settings, "EMAIL_PORT", 0)
    if not host:
        return False, "EMAIL_HOST no configurado"
    import socket
    try:
        with socket.create_connection((host, port or 25), timeout=3):
            return True, f"{host}:{port}"
    except Exception as exc:
        return False, f"no se pudo conectar a {host}:{port} — {exc}"


def _check_mercadopago():
    token = getattr(settings, "MERCADOPAGO_ACCESS_TOKEN", "") or ""
    if not token:
        return None, "no configurado"
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.mercadopago.com/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            ok = resp.status == 200
            return ok, f"HTTP {resp.status}"
    except Exception as exc:
        return False, str(exc)[:200]


def _check_telegram():
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
    if not token:
        return None, "no configurado"
    try:
        import urllib.request
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/getMe",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200, f"HTTP {resp.status}"
    except Exception as exc:
        return False, str(exc)[:200]


@staff_member_required
def health_check_view(request):
    services = []
    for name, icon, fn in (
        ("Base de datos", "database", _check_db),
        ("SMTP (correo saliente)", "mail", _check_smtp),
        ("Mercado Pago", "payments", _check_mercadopago),
        ("Telegram bot", "send", _check_telegram),
    ):
        ok, detail = fn()
        services.append({
            "name": name, "icon": icon, "ok": ok, "detail": detail,
        })

    ctx = _admin_context(
        request,
        title="Estado de servicios",
        services=services,
    )
    return render(request, "admin/health_check.html", ctx)


# ---------------------------------------------------------------------------
# Notificaciones de nueva venta — endpoint JSON para polling (#6)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Global search (#7) — endpoint JSON para el modal Cmd+K
# ---------------------------------------------------------------------------

@staff_member_required
def global_search(request):
    """Busca en pedidos, clientes, productos, planes y tickets."""
    from django.urls import reverse as _reverse
    from django.db.models import Q

    from accounts.models import User
    from catalog.models import Plan, Product
    from orders.models import Order
    from support.models import Ticket

    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({
            "orders": [], "customers": [], "products": [], "plans": [], "tickets": [],
        })

    LIMIT = 5

    # Pedidos: por uuid, email, teléfono, referencia.
    order_filter = (
        Q(email__icontains=q) | Q(phone__icontains=q) | Q(payment_reference__icontains=q)
    )
    if len(q) >= 6:
        order_filter |= Q(uuid__icontains=q)
    orders = []
    for o in Order.objects.filter(order_filter).order_by("-created_at")[:LIMIT]:
        orders.append({
            "label": f"Pedido {str(o.uuid)[:8]} — {o.email or o.phone or '—'}",
            "meta": f"{o.get_status_display()} · {o.currency} {o.total or 0}",
            "url": _reverse("admin:orders_order_change", args=[o.pk]),
        })

    # Clientes
    user_filter = (
        Q(username__icontains=q) | Q(email__icontains=q)
        | Q(first_name__icontains=q) | Q(last_name__icontains=q)
    )
    customers = []
    for u in User.objects.filter(user_filter).order_by("-id")[:LIMIT]:
        customers.append({
            "label": u.get_full_name() or u.username,
            "meta": u.email or "",
            "url": _reverse("admin:accounts_user_change", args=[u.pk]),
        })

    # Productos
    products = []
    for p in Product.objects.filter(
        Q(name__icontains=q) | Q(slug__icontains=q),
    ).order_by("-id")[:LIMIT]:
        products.append({
            "label": p.name,
            "meta": "activo" if p.is_active else "inactivo",
            "url": _reverse("admin:catalog_product_change", args=[p.pk]),
        })

    # Planes
    plans = []
    for pl in (
        Plan.objects.filter(name__icontains=q)
        .select_related("product").order_by("-id")[:LIMIT]
    ):
        plans.append({
            "label": f"{pl.product.name} — {pl.name}" if pl.product else pl.name,
            "meta": f"{pl.currency} {pl.price}",
            "url": _reverse("admin:catalog_plan_change", args=[pl.pk]),
        })

    # Tickets
    ticket_filter = Q(subject__icontains=q)
    if hasattr(Ticket, "code"):
        ticket_filter |= Q(code__icontains=q)
    tickets = []
    for t in Ticket.objects.filter(ticket_filter).order_by("-created_at")[:LIMIT]:
        tickets.append({
            "label": t.subject or f"Ticket #{t.pk}",
            "meta": t.get_status_display() if hasattr(t, "get_status_display") else "",
            "url": _reverse("admin:support_ticket_change", args=[t.pk]),
        })

    return JsonResponse({
        "orders": orders,
        "customers": customers,
        "products": products,
        "plans": plans,
        "tickets": tickets,
    })


# ---------------------------------------------------------------------------
# Reply templates JSON (#13)
# ---------------------------------------------------------------------------

@staff_member_required
def reply_templates_json(request):
    """Devuelve las plantillas activas, con body renderizado si se pasa
    `?ticket_id=N` (sustituye {nombre}, {pedido}, etc).
    """
    from support.models import ReplyTemplate, Ticket

    ticket = None
    ticket_id = request.GET.get("ticket_id")
    if ticket_id and ticket_id.isdigit():
        ticket = Ticket.objects.filter(pk=int(ticket_id)).select_related("user", "order").first()

    out = []
    for t in ReplyTemplate.objects.filter(is_active=True).order_by("category", "name"):
        out.append({
            "id": t.pk,
            "name": t.name,
            "category": t.category,
            "category_label": t.get_category_display(),
            "subject": t.subject,
            "body_rendered": t.render(ticket=ticket),
        })
    return JsonResponse({"templates": out})


@staff_member_required
def notifications_count(request):
    """Devuelve los conteos de items urgentes para el badge del header.

    El JS del admin hace polling cada N segundos a este endpoint y compara
    contra el último valor; si subió, muestra una notificación de escritorio.
    """
    from orders.models import Order
    from support.models import Ticket

    data = {
        "verifying": Order.objects.filter(status=Order.Status.VERIFYING).count(),
        "preparing": Order.objects.filter(status=Order.Status.PREPARING).count(),
        "open_tickets": Ticket.objects.exclude(
            status__in=(Ticket.Status.RESOLVED, Ticket.Status.CLOSED),
        ).count(),
    }
    data["total"] = data["verifying"] + data["preparing"] + data["open_tickets"]
    return JsonResponse(data)


# ---------------------------------------------------------------------------
# Renovaciones pendientes (#nuevo) — items próximos a vencer + 1-click renew
# ---------------------------------------------------------------------------

_RENEWAL_WINDOWS = {
    "expired": ("Vencidos", -180, 0),
    "today": ("Vencen hoy", 0, 1),
    "3d": ("Próx. 3 días", 0, 4),
    "7d": ("Próx. 7 días", 0, 8),
    "30d": ("Próx. 30 días", 0, 31),
}


@staff_member_required
def renewals_view(request):
    """Lista items próximos a vencer agrupados por filtro de ventana."""
    from orders.models import Order, OrderItem

    window_key = request.GET.get("w", "7d")
    if window_key not in _RENEWAL_WINDOWS:
        window_key = "7d"
    label, start_offset, end_offset = _RENEWAL_WINDOWS[window_key]

    now = timezone.now()
    start = now + timedelta(days=start_offset) if start_offset < 0 else now
    end = now + timedelta(days=end_offset)

    qs = (
        OrderItem.objects.filter(
            expires_at__isnull=False,
            expires_at__gte=start,
            expires_at__lt=end,
            order__status__in=(
                Order.Status.PAID,
                Order.Status.PREPARING,
                Order.Status.DELIVERED,
            ),
        )
        .select_related("order", "order__user", "product", "plan")
        .order_by("expires_at")
    )

    items = []
    for it in qs[:200]:
        days_left = (it.expires_at - now).days if it.expires_at else None
        items.append({
            "id": it.pk,
            "order_id": it.order_id,
            "order_short": str(it.order.uuid)[:8] if it.order.uuid else "",
            "customer_email": it.order.email or "",
            "customer_phone": it.order.phone or "",
            "product_name": it.product_name,
            "plan_name": it.plan_name,
            "expires_at": it.expires_at,
            "days_left": days_left,
            "reminder_3d": bool(it.expiry_reminder_3d_sent_at),
            "reminder_1d": bool(it.expiry_reminder_1d_sent_at),
            "order_change_url": reverse("admin:orders_order_change", args=[it.order_id]),
            "renew_url": reverse("admin_renew_item", args=[it.pk]),
            "whatsapp_url": _whatsapp_link(it),
        })

    ctx = _admin_context(
        request,
        title="Renovaciones pendientes",
        items=items,
        window_key=window_key,
        window_label=label,
        windows=_RENEWAL_WINDOWS,
    )
    return render(request, "admin/renewals.html", ctx)


def _whatsapp_link(item) -> str:
    """Genera un link wa.me con texto pre-rellenado para invitar al cliente
    a renovar.
    """
    import urllib.parse
    phone = (item.order.phone or "").strip().replace(" ", "").replace("+", "")
    if not phone:
        return ""
    if not phone.startswith("51") and len(phone) == 9:
        phone = "51" + phone
    fecha = item.expires_at.strftime("%d/%m/%Y") if item.expires_at else ""
    txt = (
        f"Hola! Te recordamos que tu *{item.product_name} ({item.plan_name})* "
        f"vence el {fecha}. ¿Quieres renovarlo? Te paso el link de pago."
    )
    return f"https://wa.me/{phone}?text={urllib.parse.quote(txt)}"


@staff_member_required
@require_POST
def renew_item(request, item_id: int):
    """Crea un pedido nuevo (PENDING) clonando el item original."""
    from orders.models import Order, OrderItem

    original = get_object_or_404(
        OrderItem.objects.select_related("order", "product", "plan"),
        pk=item_id,
    )

    with transaction.atomic():
        new_order = Order.objects.create(
            user=original.order.user,
            email=original.order.email,
            phone=original.order.phone,
            telegram_username=original.order.telegram_username,
            channel=Order.Channel.MANUAL,
            status=Order.Status.PENDING,
            currency=original.order.currency,
            notes=f"Renovación del pedido #{original.order_id} (item #{original.pk})",
        )
        OrderItem.objects.create(
            order=new_order,
            product=original.product,
            plan=original.plan,
            product_name=original.product_name,
            plan_name=original.plan_name,
            unit_price=original.plan.price_customer if original.plan else original.unit_price,
            quantity=original.quantity,
            requested_profile_name=original.requested_profile_name,
            requested_pin=original.requested_pin,
            customer_notes=original.customer_notes,
        )
        new_order.recompute_total()

    messages.success(
        request,
        f"Pedido de renovación #{new_order.pk} creado para "
        f"{original.order.email or original.order.phone or 'cliente'}. "
        "Ahora genera el link de pago y envíalo al cliente.",
    )
    return redirect("admin:orders_order_change", new_order.pk)
