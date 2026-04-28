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
from django.contrib.admin.views.decorators import staff_member_required
from django.db import connection
from django.db.models import Count, Max, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone


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
