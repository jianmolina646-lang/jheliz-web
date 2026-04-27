"""Dashboard callback para django-unfold.

Pinta 4 métricas arriba (Pedidos hoy, Ventas mes, Pendientes, Tickets abiertos)
+ listas rápidas de últimos pedidos y tickets.
"""

from __future__ import annotations

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

    orders_today = Order.objects.filter(created_at__date=today).count()
    sales_month = (
        Order.objects.filter(
            created_at__date__gte=first_of_month,
            status__in=[Order.Status.PAID, Order.Status.PREPARING, Order.Status.DELIVERED],
        )
        .aggregate(total=Sum("total"))
        .get("total")
        or Decimal("0.00")
    )
    pending_orders = Order.objects.filter(
        status__in=[Order.Status.PENDING, Order.Status.PAID, Order.Status.PREPARING]
    ).count()
    open_tickets = Ticket.objects.exclude(status=Ticket.Status.CLOSED).count()

    pending_distributors = User.objects.filter(
        role="distribuidor", distributor_approved=False
    ).count()

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
                    "title": "Pedidos pendientes",
                    "metric": pending_orders,
                    "footer": "Pendiente / Pagado / En preparación",
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
            "recent_orders": list(
                Order.objects.select_related("user")
                .order_by("-created_at")[:8]
            ),
            "recent_tickets": list(
                Ticket.objects.select_related("user")
                .exclude(status=Ticket.Status.CLOSED)
                .order_by("-updated_at")[:6]
            ),
            "top_products": list(
                Order.objects.filter(
                    status__in=[
                        Order.Status.PAID,
                        Order.Status.PREPARING,
                        Order.Status.DELIVERED,
                    ],
                    created_at__date__gte=first_of_month,
                )
                .values("items__product_name")
                .annotate(qty=Count("items"))
                .order_by("-qty")[:5]
            ),
        }
    )
    return context
