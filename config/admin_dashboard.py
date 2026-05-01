"""Dashboard callback para django-unfold.

Métricas + gráficos: ventas por día, top productos, método de pago,
ticket promedio, clientes nuevos vs recurrentes.
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.db.models import Count, Max, Min, Sum
from django.urls import reverse
from django.utils import timezone


def dashboard_callback(request, context):
    from orders.models import Order, OrderItem, ReminderRunLog
    from support.models import Ticket
    from accounts.models import User
    from catalog.models import Plan, Product, ProductReview, StockItem

    now = timezone.localtime()
    today = now.date()
    yesterday = today - timedelta(days=1)
    first_of_month = today.replace(day=1)
    paid_statuses = [Order.Status.PAID, Order.Status.PREPARING, Order.Status.DELIVERED]

    # ---- KPIs arriba ---------------------------------------------------------
    orders_today = Order.objects.filter(created_at__date=today).count()
    sales_month = (
        Order.objects.filter(
            created_at__date__gte=first_of_month,
            status__in=paid_statuses,
        )
        .aggregate(total=Sum("total"))
        .get("total")
        or Decimal("0.00")
    )
    pending_orders = Order.objects.filter(
        status__in=[Order.Status.PENDING, Order.Status.PAID, Order.Status.PREPARING]
    ).count()
    verifying_orders = Order.objects.filter(status=Order.Status.VERIFYING).count()
    open_tickets = Ticket.objects.exclude(status=Ticket.Status.CLOSED).count()

    # Pedidos "esperando stock": en PREPARING con al menos un item que
    # todavía no tiene credenciales ni stock vinculado. Son los que el
    # admin necesita resolver (cargar stock o entregar manualmente).
    waiting_stock_orders = (
        Order.objects.filter(status=Order.Status.PREPARING)
        .filter(
            models.Q(items__delivered_credentials="")
            & models.Q(items__stock_item__isnull=True)
        )
        .distinct()
        .count()
    )

    # Ticket promedio + nuevos vs recurrentes del mes
    paid_month_qs = Order.objects.filter(
        created_at__date__gte=first_of_month, status__in=paid_statuses
    )
    paid_month_count = paid_month_qs.count()
    avg_ticket = (
        (sales_month / paid_month_count) if paid_month_count else Decimal("0.00")
    )
    # Una sola query agrega min/max de fechas pagadas por usuario. Antes había
    # un .exists() por cliente (N+1 grave en cuanto crece la lista de clientes).
    user_paid_range = (
        Order.objects
        .filter(status__in=paid_statuses, user__isnull=False)
        .values("user_id")
        .annotate(
            first_paid=Min("created_at__date"),
            last_paid=Max("created_at__date"),
        )
    )
    new_customers = 0
    returning_customers = 0
    for row in user_paid_range:
        if row["last_paid"] is None or row["last_paid"] < first_of_month:
            continue  # no compró este mes
        if row["first_paid"] and row["first_paid"] < first_of_month:
            returning_customers += 1
        else:
            new_customers += 1

    pending_distributors = User.objects.filter(
        role="distribuidor", distributor_approved=False
    ).count()

    # ---- Operacional: ventas hoy vs ayer + cuentas por vencer ---------------
    sales_today = (
        Order.objects.filter(created_at__date=today, status__in=paid_statuses)
        .aggregate(total=Sum("total")).get("total") or Decimal("0.00")
    )
    sales_yesterday = (
        Order.objects.filter(created_at__date=yesterday, status__in=paid_statuses)
        .aggregate(total=Sum("total")).get("total") or Decimal("0.00")
    )
    if sales_yesterday > 0:
        delta_pct = float((sales_today - sales_yesterday) / sales_yesterday * 100)
    elif sales_today > 0:
        delta_pct = 100.0
    else:
        delta_pct = 0.0

    # Cuentas que vencen hoy / mañana / próximos 3 días.
    expiring_today = OrderItem.objects.filter(
        expires_at__date=today, order__status=Order.Status.DELIVERED,
    ).count()
    expiring_tomorrow = OrderItem.objects.filter(
        expires_at__date=today + timedelta(days=1),
        order__status=Order.Status.DELIVERED,
    ).count()
    expiring_soon = OrderItem.objects.filter(
        expires_at__date__gte=today,
        expires_at__date__lte=today + timedelta(days=3),
        order__status=Order.Status.DELIVERED,
    ).select_related("order", "order__user")[:8]

    # Stock bajo: productos activos con menos de 3 stocks disponibles.
    low_stock_rows = []
    for p in Product.objects.filter(is_active=True).order_by("name"):
        avail = StockItem.objects.filter(
            product=p, status=StockItem.Status.AVAILABLE
        ).count()
        if avail < 3:
            low_stock_rows.append({"product": p, "available": avail})
        if len(low_stock_rows) >= 8:
            break

    # Tickets esperando respuesta del soporte (estado abierto o pending_admin).
    pending_support_tickets = Ticket.objects.filter(
        status__in=[Ticket.Status.OPEN, Ticket.Status.PENDING_ADMIN],
    ).count()

    # Reseñas pendientes de moderación.
    pending_reviews = ProductReview.objects.filter(
        status=ProductReview.Status.PENDING,
    ).count()

    # Planes activos sin stock disponible (crítico).
    out_of_stock = (
        Plan.objects.filter(is_active=True, product__is_active=True)
        .annotate(
            avail=Count(
                "stock_items",
                filter=models.Q(stock_items__status=StockItem.Status.AVAILABLE),
            )
        )
        .filter(avail=0)
        .count()
    )

    # ---- Chart 1: ventas por día (últimos 14 días) --------------------------
    days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    per_day_rows = {
        d: Decimal("0.00") for d in days
    }
    per_day_qs = (
        Order.objects.filter(
            created_at__date__gte=days[0],
            status__in=paid_statuses,
        )
        .values("created_at__date")
        .annotate(total=Sum("total"))
    )
    for row in per_day_qs:
        d = row["created_at__date"]
        if d in per_day_rows:
            per_day_rows[d] = row["total"] or Decimal("0.00")
    sales_chart = {
        "labels": [d.strftime("%d %b") for d in days],
        "data": [float(per_day_rows[d]) for d in days],
    }

    # ---- Chart 2: top 5 productos del mes -----------------------------------
    top_products_rows = list(
        Order.objects.filter(
            status__in=paid_statuses,
            created_at__date__gte=first_of_month,
        )
        .values("items__product_name")
        .annotate(qty=Count("items"))
        .order_by("-qty")[:5]
    )
    top_chart = {
        "labels": [r["items__product_name"] or "—" for r in top_products_rows],
        "data": [r["qty"] for r in top_products_rows],
    }

    # ---- Chart 3: método de pago (mes) --------------------------------------
    method_rows = (
        paid_month_qs.values("payment_provider").annotate(qty=Count("id"))
    )
    method_labels = []
    method_data = []
    for r in method_rows:
        name = r["payment_provider"] or "—"
        pretty = {"mercadopago": "Mercado Pago", "yape": "Yape directo"}.get(name, name)
        method_labels.append(pretty)
        method_data.append(r["qty"])
    method_chart = {"labels": method_labels, "data": method_data}

    # ---- Chart 4: stock vs ventas (top productos) ---------------------------
    # Útil para saber qué reponer: barras de "stock disponible" vs "vendidos
    # últimos 7 días" lado a lado.
    last_7d = today - timedelta(days=6)
    sold_per_product = (
        OrderItem.objects.filter(
            order__created_at__date__gte=last_7d,
            order__status__in=paid_statuses,
        )
        .values("product_id", "product_name")
        .annotate(sold=Count("id"))
    )
    sold_map = {r["product_id"]: r["sold"] for r in sold_per_product}
    sold_name_map = {r["product_id"]: r["product_name"] for r in sold_per_product}

    available_per_product = (
        StockItem.objects.filter(status=StockItem.Status.AVAILABLE)
        .values("product_id", "product__name")
        .annotate(avail=Count("id"))
    )
    avail_map = {r["product_id"]: r["avail"] for r in available_per_product}
    avail_name_map = {r["product_id"]: r["product__name"] for r in available_per_product}

    stock_product_ids = set(sold_map.keys()) | set(avail_map.keys())
    stock_rows = []
    for pid in stock_product_ids:
        name = sold_name_map.get(pid) or avail_name_map.get(pid) or "—"
        stock_rows.append({
            "name": name,
            "available": avail_map.get(pid, 0),
            "sold": sold_map.get(pid, 0),
        })
    # Orden: primero los que tienen más ventas pero menos stock (urgente
    # reponer), después los que solo tienen stock alto sin ventas.
    stock_rows.sort(
        key=lambda r: (
            -(r["sold"] - min(r["available"], r["sold"])),
            -r["sold"],
            r["available"],
        )
    )
    stock_rows = stock_rows[:8]
    stock_chart = {
        "labels": [r["name"] for r in stock_rows],
        "available": [r["available"] for r in stock_rows],
        "sold": [r["sold"] for r in stock_rows],
    }

    arrow = "↑" if delta_pct >= 0 else "↓"

    # ---- Saludo personalizado para el header del dashboard ------------------
    hour = now.hour
    if hour < 12:
        greeting = "Buenos días"
    elif hour < 19:
        greeting = "Buenas tardes"
    else:
        greeting = "Buenas noches"
    user_first_name = (
        getattr(request.user, "first_name", "")
        or getattr(request.user, "username", "")
        or ""
    ).split()[0] if hasattr(request, "user") else ""

    # ---- Necesita acción: lista consolidada de cosas urgentes ---------------
    # Tones limited to colors compiled in Unfold's Tailwind: red, orange, yellow, green, blue.
    _TONE_CLASSES = {
        "red": "border-red-500 bg-red-500/20 text-red-100",
        "orange": "border-orange-500 bg-orange-500/20 text-orange-100",
        "yellow": "border-yellow-500 bg-yellow-500/20 text-yellow-100",
        "green": "border-green-500 bg-green-500/20 text-green-100",
        "blue": "border-blue-500 bg-blue-500/20 text-blue-100",
    }
    needs_action = []
    if verifying_orders:
        needs_action.append({
            "label": "Comprobantes Yape por verificar",
            "count": verifying_orders, "icon": "qr_code_scanner", "tone": "orange",
            "link": reverse("admin:orders_order_yape_inbox"),
        })
    if pending_orders:
        needs_action.append({
            "label": "Pedidos en preparación",
            "count": pending_orders, "icon": "pending_actions", "tone": "yellow",
            "link": reverse("admin:orders_order_changelist") + "?status__exact=preparing",
        })
    if waiting_stock_orders:
        needs_action.append({
            "label": "Pedidos esperando stock",
            "count": waiting_stock_orders, "icon": "inventory_2", "tone": "red",
            "link": reverse("admin:orders_order_changelist") + "?status__exact=preparing",
        })
    if pending_support_tickets:
        needs_action.append({
            "label": "Tickets sin responder",
            "count": pending_support_tickets, "icon": "support_agent", "tone": "blue",
            "link": reverse("admin:support_ticket_changelist"),
        })
    if pending_reviews:
        needs_action.append({
            "label": "Reseñas pendientes de aprobar",
            "count": pending_reviews, "icon": "rate_review", "tone": "blue",
            "link": reverse("admin:catalog_productreview_changelist") + "?status__exact=pending",
        })
    if pending_distributors:
        needs_action.append({
            "label": "Distribuidores por aprobar",
            "count": pending_distributors, "icon": "verified_user", "tone": "green",
            "link": reverse("admin:accounts_user_changelist") + "?role__exact=distribuidor&distributor_approved__exact=0",
        })
    if out_of_stock:
        needs_action.append({
            "label": "Planes SIN stock (críticos)",
            "count": out_of_stock, "icon": "warning", "tone": "red",
            "link": reverse("admin:catalog_stockitem_changelist") + "?status__exact=available",
        })
    if expiring_today:
        needs_action.append({
            "label": "Cuentas que vencen HOY",
            "count": expiring_today, "icon": "schedule", "tone": "orange",
            "link": reverse("admin:orders_orderitem_changelist"),
        })
    for item in needs_action:
        item["classes"] = _TONE_CLASSES[item["tone"]]

    context.update(
        {
            "dashboard_greeting": greeting,
            "dashboard_user_first_name": user_first_name,
            "dashboard_orders_today": orders_today,
            "dashboard_sales_today": sales_today,
            "dashboard_pending_orders_count": pending_orders + verifying_orders,
            "needs_action": needs_action,
            "kpi": [
                {
                    "title": "Ventas hoy",
                    "metric": f"S/ {sales_today:,.2f}",
                    "footer": f"{arrow} {abs(delta_pct):.0f}% vs ayer (S/ {sales_yesterday:,.2f})",
                    "icon": "trending_up",
                    "link": reverse("admin:orders_order_changelist") + "?status__exact=delivered",
                },
                {
                    "title": "Pedidos hoy",
                    "metric": orders_today,
                    "footer": f"{now.strftime('%d %b %Y')}",
                    "icon": "today",
                    "link": reverse("admin:orders_order_changelist"),
                },
                {
                    "title": "Ventas del mes",
                    "metric": f"S/ {sales_month:,.2f}",
                    "footer": f"Desde {first_of_month.strftime('%d %b')}",
                    "icon": "payments",
                    "link": reverse("admin:orders_order_changelist") + "?status__exact=delivered",
                },
                {
                    "title": "Ticket promedio",
                    "metric": f"S/ {avg_ticket:,.2f}",
                    "footer": f"{paid_month_count} pedidos pagados",
                    "icon": "receipt_long",
                    "link": reverse("admin:orders_order_changelist"),
                },
                {
                    "title": "Yape por verificar",
                    "metric": verifying_orders,
                    "footer": "Comprobantes pendientes",
                    "icon": "qr_code_scanner",
                    "link": reverse("admin:orders_order_yape_inbox"),
                },
                {
                    "title": "Pedidos pendientes",
                    "metric": pending_orders,
                    "footer": "Pendiente / Pagado / En prep.",
                    "icon": "pending_actions",
                    "link": reverse("admin:orders_order_changelist") + "?status__exact=preparing",
                },
                {
                    "title": "Tickets sin responder",
                    "metric": pending_support_tickets,
                    "footer": "Esperan tu respuesta",
                    "icon": "support_agent",
                    "link": reverse("admin:support_ticket_changelist"),
                },
                {
                    "title": "Reseñas por moderar",
                    "metric": pending_reviews,
                    "footer": "Aprobar / rechazar",
                    "icon": "rate_review",
                    "link": reverse("admin:catalog_productreview_changelist") + "?status__exact=pending",
                },
                {
                    "title": "Vencen hoy",
                    "metric": expiring_today,
                    "footer": f"+{expiring_tomorrow} mañana",
                    "icon": "schedule",
                    "link": reverse("admin:orders_orderitem_changelist"),
                },
            ],
            "pending_distributors": pending_distributors,
            "expiring_soon": expiring_soon,
            "low_stock_rows": low_stock_rows,
            "new_vs_returning": {
                "new": new_customers,
                "returning": returning_customers,
            },
            "sales_chart_json": json.dumps(sales_chart),
            "top_chart_json": json.dumps(top_chart),
            "method_chart_json": json.dumps(method_chart),
            "stock_chart_json": json.dumps(stock_chart),
            "recent_orders": list(
                Order.objects.select_related("user")
                .order_by("-created_at")[:8]
            ),
            "recent_tickets": list(
                Ticket.objects.select_related("user")
                .exclude(status=Ticket.Status.CLOSED)
                .order_by("-updated_at")[:6]
            ),
            "top_products": top_products_rows,
            "reminder_status": _reminder_status(ReminderRunLog, now),
        }
    )
    return context


def _reminder_status(ReminderRunLog, now) -> dict:
    """Estado del último run de ``send_expiry_reminders`` para el dashboard."""
    last = (
        ReminderRunLog.objects.exclude(dry_run=True)
        .order_by("-started_at")
        .first()
    )
    if last is None:
        return {
            "has_runs": False,
            "tone": "amber",
            "label": "Aún no corrió ningún recordatorio",
            "details": "El comando send_expiry_reminders no se ejecutó todavía.",
            "history_url": reverse("admin:orders_reminderrunlog_changelist"),
        }
    hours_ago = (now - last.started_at).total_seconds() / 3600
    customer = last.customer_count or 0
    distri = last.distri_count or 0
    total = customer + distri
    if last.error:
        tone = "red"
        label = "Último run falló"
    elif hours_ago > 25:
        tone = "red"
        label = f"Último run hace {int(hours_ago)} h — el cron podría estar caído"
    elif hours_ago > 12:
        tone = "amber"
        label = f"Último run hace {int(hours_ago)} h"
    else:
        tone = "emerald"
        label = (
            "Sin avisos pendientes hoy"
            if total == 0
            else f"{total} aviso{'s' if total != 1 else ''} enviado{'s' if total != 1 else ''} hoy"
        )
    return {
        "has_runs": True,
        "tone": tone,
        "label": label,
        "details": f"{customer} cliente(s) · {distri} distribuidor(es)",
        "by_window": last.by_window or {},
        "started_at": last.started_at,
        "finished_at": last.finished_at,
        "error": last.error,
        "history_url": reverse("admin:orders_reminderrunlog_changelist"),
    }
