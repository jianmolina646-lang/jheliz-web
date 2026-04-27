"""Dashboard callback para django-unfold.

Métricas + gráficos: ventas por día, top productos, método de pago,
ticket promedio, clientes nuevos vs recurrentes.
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.urls import reverse
from django.utils import timezone


def dashboard_callback(request, context):
    from orders.models import Order
    from support.models import Ticket
    from accounts.models import User

    now = timezone.localtime()
    today = now.date()
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

    # Ticket promedio + nuevos vs recurrentes del mes
    paid_month_qs = Order.objects.filter(
        created_at__date__gte=first_of_month, status__in=paid_statuses
    )
    paid_month_count = paid_month_qs.count()
    avg_ticket = (
        (sales_month / paid_month_count) if paid_month_count else Decimal("0.00")
    )
    customers_month = (
        paid_month_qs.exclude(user__isnull=True)
        .values_list("user_id", flat=True)
        .distinct()
    )
    new_customers = 0
    returning_customers = 0
    for uid in customers_month:
        older = Order.objects.filter(
            user_id=uid,
            status__in=paid_statuses,
            created_at__date__lt=first_of_month,
        ).exists()
        if older:
            returning_customers += 1
        else:
            new_customers += 1

    pending_distributors = User.objects.filter(
        role="distribuidor", distributor_approved=False
    ).count()

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

    context.update(
        {
            "kpi": [
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
                    "link": reverse("admin:orders_order_changelist") + "?status__exact=verifying",
                },
                {
                    "title": "Pedidos pendientes",
                    "metric": pending_orders,
                    "footer": "Pendiente / Pagado / En prep.",
                    "icon": "pending_actions",
                    "link": reverse("admin:orders_order_changelist") + "?status__exact=preparing",
                },
                {
                    "title": "Tickets abiertos",
                    "metric": open_tickets,
                    "footer": "Excluye cerrados",
                    "icon": "support_agent",
                    "link": reverse("admin:support_ticket_changelist"),
                },
            ],
            "pending_distributors": pending_distributors,
            "new_vs_returning": {
                "new": new_customers,
                "returning": returning_customers,
            },
            "sales_chart_json": json.dumps(sales_chart),
            "top_chart_json": json.dumps(top_chart),
            "method_chart_json": json.dumps(method_chart),
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
        }
    )
    return context
