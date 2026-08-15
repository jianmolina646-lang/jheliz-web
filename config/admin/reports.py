"""Reporte financiero visual del panel administrativo."""

from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone


def _admin_context(request, **extra):
    """Contexto base para que la vista herede de admin/base.html."""
    return {
        **admin.site.each_context(request),
        **extra,
    }


@staff_member_required
def reports_view(request):
    """Reportes de ventas: hoy, 7d, 30d + top productos + ingreso por método.

    Además incluye:
    - Comparativas vs el período anterior (delta absoluto y porcentual).
    - Serie diaria de revenue para sparkline (últimos 30 días).
    - Ticket promedio y métricas derivadas.
    - Íconos/emojis por producto y por método de pago para el render.
    """
    from catalog.models import Product
    from orders.models import Order, OrderItem

    today = timezone.localdate()
    paid_statuses = (
        Order.Status.PAID, Order.Status.PREPARING, Order.Status.DELIVERED,
    )
    paid_qs = Order.objects.filter(status__in=paid_statuses)

    def _range(days, *, offset=0):
        """Agrega ``count`` y ``revenue`` para una ventana móvil reciente.

        ``offset=0`` es el período actual (últimos N días). ``offset=days``
        es el período anterior inmediatamente previo (días N..2N hacia atrás)
        — sirve para mostrar deltas vs el período pasado.
        """
        end = timezone.now() - timedelta(days=offset)
        start = end - timedelta(days=days)
        agg = paid_qs.filter(paid_at__gte=start, paid_at__lt=end).aggregate(
            count=Count("id"), revenue=Sum("total"),
        )
        return {
            "count": agg["count"] or 0,
            "revenue": agg["revenue"] or Decimal("0"),
        }

    def _with_delta(current, previous):
        cur_rev = current["revenue"]
        prev_rev = previous["revenue"]
        delta_abs = cur_rev - prev_rev
        if prev_rev > 0:
            pct = float((cur_rev - prev_rev) / prev_rev) * 100.0
        elif cur_rev > 0:
            pct = 100.0
        else:
            pct = 0.0
        if pct > 0:
            tone = "success"; arrow = "▲"
        elif pct < 0:
            tone = "danger"; arrow = "▼"
        else:
            tone = "neutral"; arrow = "→"
        avg_ticket = (cur_rev / current["count"]) if current["count"] else Decimal("0")
        return {
            **current,
            "delta_abs": delta_abs,
            "delta_pct": round(pct, 1),
            "delta_tone": tone,
            "delta_arrow": arrow,
            "avg_ticket": avg_ticket,
        }

    today_start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    yesterday_start = today_start - timedelta(days=1)
    today_stats_agg = paid_qs.filter(paid_at__gte=today_start).aggregate(
        count=Count("id"), revenue=Sum("total"),
    )
    yest_stats_agg = paid_qs.filter(
        paid_at__gte=yesterday_start, paid_at__lt=today_start,
    ).aggregate(count=Count("id"), revenue=Sum("total"))
    today_stats = _with_delta(
        {
            "count": today_stats_agg["count"] or 0,
            "revenue": today_stats_agg["revenue"] or Decimal("0"),
        },
        {
            "count": yest_stats_agg["count"] or 0,
            "revenue": yest_stats_agg["revenue"] or Decimal("0"),
        },
    )
    week_stats = _with_delta(_range(7), _range(7, offset=7))
    month_stats = _with_delta(_range(30), _range(30, offset=30))
    year_stats = _with_delta(_range(365), _range(365, offset=365))

    # Serie diaria de revenue (últimos 30 días) para el sparkline/chart.
    last_30 = timezone.now() - timedelta(days=30)
    daily_qs = (
        paid_qs.filter(paid_at__gte=last_30)
        .extra(select={"day": "date(paid_at)"})
        .values("day")
        .annotate(revenue=Sum("total"), count=Count("id"))
        .order_by("day")
    )
    daily_map = {row["day"]: row for row in daily_qs}
    # Normalizar a 30 días con 0s donde no hubo ventas.
    daily_raw = []
    daily_max_rev = Decimal("0")
    for offset_days in range(29, -1, -1):
        d = today - timedelta(days=offset_days)
        # daily_map keys may be either ``date`` or ``str`` (sqlite vs postgres).
        row = daily_map.get(d) or daily_map.get(d.isoformat()) or {}
        rev = row.get("revenue") or Decimal("0")
        cnt = row.get("count") or 0
        daily_max_rev = max(daily_max_rev, rev)
        daily_raw.append({"day": d, "revenue": rev, "count": cnt})

    # Precomputo posiciones SVG (viewBox 300x90, 30 barras de width=9).
    daily_series = []
    for i, row in enumerate(daily_raw):
        rev = row["revenue"]
        if daily_max_rev > 0:
            bar_h = float(rev) / float(daily_max_rev) * 80.0
        else:
            bar_h = 0.0
        daily_series.append({
            **row,
            # Strings con punto decimal (evita localización a coma en SVG).
            "x": f"{i * 10}",
            "y": f"{85.0 - bar_h:.2f}",
            "h": f"{bar_h:.2f}",
        })

    # Top productos por revenue (últimos 30 días) — agrego ícono y % del total.
    from django.db.models import F

    top_products_qs = (
        OrderItem.objects
        .filter(order__status__in=paid_statuses, order__paid_at__gte=last_30)
        .values("product_name", "product_id")
        .annotate(
            units=Sum("quantity"),
            revenue=Sum(F("unit_price") * F("quantity")),
        )
        .order_by("-revenue")[:10]
    )
    top_products = list(top_products_qs)
    total_top_rev = sum((p["revenue"] or Decimal("0")) for p in top_products) or Decimal("1")
    icon_map = {
        p.pk: (p.icon or (p.category.emoji if p.category_id else "") or "\U0001F3AC")
        for p in Product.objects.filter(pk__in=[
            p["product_id"] for p in top_products if p.get("product_id")
        ]).select_related("category")
    }
    for p in top_products:
        p["icon"] = icon_map.get(p.get("product_id"), "\U0001F3AC")
        p["pct"] = float((p["revenue"] or Decimal("0")) / total_top_rev * 100)

    # Ingresos por método de pago (últimos 30 días) — agrego ícono y tono.
    method_visuals = {
        "yape":         {"icon": "\U0001F4F1", "tone": "violet",  "label": "Yape"},
        "binance":      {"icon": "\U0001FA99", "tone": "warning", "label": "Binance Pay"},
        "bank":         {"icon": "\U0001F3E6", "tone": "info",    "label": "Dep\u00f3sito bancario"},
        "mercadopago":  {"icon": "\U0001F4B3", "tone": "info",    "label": "Mercado Pago"},
        "wallet":       {"icon": "\U0001F4B0", "tone": "success", "label": "Saldo wallet"},
        "manual":       {"icon": "\U0001F91D", "tone": "neutral", "label": "Manual"},
        "transferencia":{"icon": "\U0001F3E6", "tone": "info",    "label": "Transferencia"},
    }
    by_method_qs = (
        paid_qs.filter(paid_at__gte=last_30)
        .values("payment_provider")
        .annotate(count=Count("id"), revenue=Sum("total"))
        .order_by("-revenue")
    )
    by_method = list(by_method_qs)
    total_method_rev = sum((m["revenue"] or Decimal("0")) for m in by_method) or Decimal("1")
    for m in by_method:
        key = (m["payment_provider"] or "").lower()
        viz = method_visuals.get(key, {
            "icon": "\U0001F4B3", "tone": "neutral", "label": m["payment_provider"] or "—",
        })
        m.update(viz)
        m["pct"] = float((m["revenue"] or Decimal("0")) / total_method_rev * 100)

    kpi_cards = [
        {"slug": "today", "label": "Hoy",              "emoji": "\u2600\ufe0f", "stats": today_stats},
        {"slug": "week",  "label": "Últimos 7 días",   "emoji": "\U0001F4C5", "stats": week_stats},
        {"slug": "month", "label": "Últimos 30 días",  "emoji": "\U0001F4CA", "stats": month_stats},
        {"slug": "year",  "label": "Últimos 365 días", "emoji": "\U0001F3C6", "stats": year_stats},
    ]

    ctx = _admin_context(
        request,
        title="Reportes financieros",
        today_stats=today_stats,
        week_stats=week_stats,
        month_stats=month_stats,
        year_stats=year_stats,
        kpi_cards=kpi_cards,
        top_products=top_products,
        by_method=by_method,
        daily_series=daily_series,
        daily_max_rev=daily_max_rev,
        currency_symbol=settings.DEFAULT_CURRENCY_SYMBOL,
    )
    return render(request, "admin/reports.html", ctx)
