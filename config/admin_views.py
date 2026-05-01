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
from django.db.models import Count, F, Max, Q, Sum
from django.contrib import admin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.response import TemplateResponse
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

def _perform_global_search(q: str, limit: int):
    """Ejecuta la búsqueda cruzada y devuelve un dict con los grupos encontrados.

    Se usa tanto desde el endpoint JSON (modal Cmd+K) como desde la página
    de resultados HTML (`/jheliz-admin/search/?q=...&full=1`).
    """
    from django.urls import reverse as _reverse
    from django.db.models import Q
    from django.db.models.functions import Cast
    from django.db.models import CharField as _CharField

    from accounts.models import User
    from catalog.models import Plan, Product
    from orders.models import Order
    from support.models import Ticket

    q = (q or "").strip()
    empty = {"orders": [], "customers": [], "products": [], "plans": [], "tickets": []}
    if len(q) < 2:
        return empty

    # Pedidos: uuid (string), email, teléfono, referencia, telegram, notas.
    # UUIDField no matchea bien con icontains en todos los backends; casteamos
    # a CharField para búsquedas parciales reales.
    order_qs = Order.objects.annotate(uuid_str=Cast("uuid", _CharField()))
    order_filter = (
        Q(email__icontains=q)
        | Q(phone__icontains=q)
        | Q(payment_reference__icontains=q)
        | Q(telegram_username__icontains=q)
        | Q(notes__icontains=q)
        | Q(uuid_str__icontains=q)
    )
    orders = []
    for o in order_qs.filter(order_filter).order_by("-created_at")[:limit]:
        orders.append({
            "label": f"Pedido {str(o.uuid)[:8]} — {o.email or o.phone or o.telegram_username or '—'}",
            "meta": f"{o.get_status_display()} · {o.currency} {o.total or 0}",
            "url": _reverse("admin:orders_order_change", args=[o.pk]),
        })

    # Clientes / distribuidores
    user_filter = (
        Q(username__icontains=q)
        | Q(email__icontains=q)
        | Q(first_name__icontains=q)
        | Q(last_name__icontains=q)
        | Q(phone__icontains=q)
        | Q(telegram_username__icontains=q)
    )
    customers = []
    for u in User.objects.filter(user_filter).order_by("-id")[:limit]:
        full = u.get_full_name() or u.username
        role = u.get_role_display() if hasattr(u, "get_role_display") else ""
        meta_parts = [p for p in [u.email, role] if p]
        customers.append({
            "label": full,
            "meta": " · ".join(meta_parts),
            "url": _reverse("admin:accounts_user_change", args=[u.pk]),
        })

    # Productos
    products = []
    for p in Product.objects.filter(
        Q(name__icontains=q) | Q(slug__icontains=q),
    ).order_by("-id")[:limit]:
        products.append({
            "label": p.name,
            "meta": "activo" if p.is_active else "inactivo",
            "url": _reverse("admin:catalog_product_change", args=[p.pk]),
        })

    # Planes
    plans = []
    for pl in (
        Plan.objects.filter(name__icontains=q)
        .select_related("product").order_by("-id")[:limit]
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
    for t in Ticket.objects.filter(ticket_filter).order_by("-created_at")[:limit]:
        tickets.append({
            "label": t.subject or f"Ticket #{t.pk}",
            "meta": t.get_status_display() if hasattr(t, "get_status_display") else "",
            "url": _reverse("admin:support_ticket_change", args=[t.pk]),
        })

    return {
        "orders": orders,
        "customers": customers,
        "products": products,
        "plans": plans,
        "tickets": tickets,
    }


@staff_member_required
def global_search(request):
    """Búsqueda cruzada en el admin.

    Dos modos de respuesta:
    - JSON (default, usado por el modal Cmd+K con top 5 por sección).
    - HTML cuando se pasa ``?full=1``: página de resultados con top 25 por
      sección, pensada para cuando el modal no alcanza.
    """
    q = (request.GET.get("q") or "").strip()
    full = request.GET.get("full") == "1"
    limit = 25 if full else 5
    groups = _perform_global_search(q, limit=limit)

    if full:
        total = sum(len(v) for v in groups.values())
        context = {
            **admin.site.each_context(request),
            "title": f"Búsqueda global: {q}" if q else "Búsqueda global",
            "q": q,
            "groups": groups,
            "total": total,
            "limit": limit,
        }
        return TemplateResponse(
            request, "admin/global_search_results.html", context,
        )
    return JsonResponse(groups)


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


def _humanize_delta(delta: timedelta) -> str:
    """Devuelve un string corto en español tipo 'hace 5 min', 'hace 2 h'."""
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return "hace unos segundos"
    minutes = seconds // 60
    if minutes < 60:
        return f"hace {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"hace {hours} h"
    days = hours // 24
    return f"hace {days} d"


def _format_money(amount: Decimal | None, currency: str | None = None) -> str:
    """Formatea un Decimal como 'S/49.90' (o el símbolo configurado)."""
    if amount is None:
        return ""
    symbol = (currency or settings.DEFAULT_CURRENCY_SYMBOL or "S/").strip()
    try:
        return f"{symbol}{Decimal(amount).quantize(Decimal('0.01'))}"
    except Exception:
        return f"{symbol}{amount}"


@staff_member_required
def notifications_count(request):
    """Endpoint JSON consumido por el bell de notificaciones del admin.

    Devuelve dos cosas:

    * Contadores agregados por categoría (compat con el JS viejo del dashboard).
    * Una lista ``items`` con los pendientes más recientes (Yape por aprobar,
      pedidos en preparación, tickets abiertos), enriquecida con la info que el
      bell muestra inline: título, subtítulo, URL al admin y timestamp.

    El JS hace polling cada 30s y compara contra ``localStorage`` para saber
    cuáles items son nuevos vs ya vistos.
    """
    from orders.models import Order
    from support.models import Ticket

    now = timezone.now()
    item_limit = 8  # por categoría, antes de hacer merge final

    verifying_qs = (
        Order.objects.filter(status=Order.Status.VERIFYING)
        .order_by("-payment_proof_uploaded_at", "-created_at")[:item_limit]
    )
    preparing_qs = (
        Order.objects.filter(status=Order.Status.PREPARING)
        .order_by("-paid_at", "-created_at")[:item_limit]
    )
    tickets_qs = (
        Ticket.objects.exclude(
            status__in=(Ticket.Status.RESOLVED, Ticket.Status.CLOSED),
        ).select_related("user").order_by("-created_at")[:item_limit]
    )

    items: list[dict] = []

    def _order_subtitle(order: Order) -> str:
        provider = (order.payment_provider or "").strip().capitalize() or "Pago"
        contact = order.email or order.phone or order.telegram_username or "cliente"
        return f"{provider} · {contact}"

    for order in verifying_qs:
        ts = order.payment_proof_uploaded_at or order.created_at
        items.append({
            "id": f"order-verifying-{order.pk}",
            "kind": "yape_proof",
            "icon": "hourglass_top",
            "title": f"Comprobante por aprobar · #{order.short_uuid} · {_format_money(order.total, order.currency)}",
            "subtitle": _order_subtitle(order),
            "url": reverse("admin:orders_order_change", args=[order.pk]),
            "created_at": ts.isoformat() if ts else None,
            "relative": _humanize_delta(now - ts) if ts else "",
        })

    for order in preparing_qs:
        ts = order.paid_at or order.created_at
        items.append({
            "id": f"order-preparing-{order.pk}",
            "kind": "preparing",
            "icon": "inventory",
            "title": f"Pedido en preparación · #{order.short_uuid} · {_format_money(order.total, order.currency)}",
            "subtitle": _order_subtitle(order),
            "url": reverse("admin:orders_order_change", args=[order.pk]),
            "created_at": ts.isoformat() if ts else None,
            "relative": _humanize_delta(now - ts) if ts else "",
        })

    for ticket in tickets_qs:
        ts = ticket.created_at
        author_label = ticket.user.email or ticket.user.get_username()
        subject = (ticket.subject or "Sin asunto").strip()
        items.append({
            "id": f"ticket-{ticket.pk}",
            "kind": "ticket",
            "icon": "support_agent",
            "title": f"Ticket abierto · {subject[:60]}",
            "subtitle": author_label,
            "url": reverse("admin:support_ticket_change", args=[ticket.pk]),
            "created_at": ts.isoformat() if ts else None,
            "relative": _humanize_delta(now - ts) if ts else "",
        })

    # Más recientes primero, máximo 15 visibles en el bell.
    items.sort(key=lambda x: x["created_at"] or "", reverse=True)
    items = items[:15]

    counts = {
        "verifying": Order.objects.filter(status=Order.Status.VERIFYING).count(),
        "preparing": Order.objects.filter(status=Order.Status.PREPARING).count(),
        "open_tickets": Ticket.objects.exclude(
            status__in=(Ticket.Status.RESOLVED, Ticket.Status.CLOSED),
        ).count(),
    }
    counts["total"] = counts["verifying"] + counts["preparing"] + counts["open_tickets"]

    # Compat: el JS viejo del dashboard espera las claves verifying/preparing/total
    # en el nivel raíz; las dejamos ahí + un bloque "counts" duplicado para JS nuevo.
    return JsonResponse({
        **counts,
        "counts": counts,
        "items": items,
        "generated_at": now.isoformat(),
    })


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


# ---------------------------------------------------------------------------
# Stock — módulo unificado: Resumen · Cuentas · Importar
# ---------------------------------------------------------------------------

def _stock_cards_and_kpis():
    """Devuelve (cards ordenadas, kpis) para el dashboard de stock.

    Reutilizado por el header común y por la vista resumen.
    """
    from catalog.models import Product, StockItem

    products = (
        Product.objects.filter(is_active=True)
        .order_by("category__order", "order", "name")
    )

    by_product: dict[int, dict] = {}
    for p in products:
        by_product[p.pk] = {
            "product": p,
            "available": 0,
            "sold": 0,
            "reserved": 0,
            "defective": 0,
            "disabled": 0,
            "total": 0,
            "low_stock_threshold": 0,
        }
        if p.plans.exists():
            by_product[p.pk]["low_stock_threshold"] = max(
                (pl.low_stock_threshold for pl in p.plans.all()), default=3
            )

    counts = (
        StockItem.objects.values("product_id", "status")
        .annotate(c=Count("id"))
    )
    for row in counts:
        if row["product_id"] in by_product:
            data = by_product[row["product_id"]]
            data[row["status"]] = row["c"]
            data["total"] += row["c"]

    cards = []
    for data in by_product.values():
        avail = data["available"]
        threshold = data["low_stock_threshold"] or 3
        if avail == 0:
            level = "empty"
        elif avail < threshold:
            level = "low"
        else:
            level = "ok"
        cards.append({**data, "level": level})

    cards.sort(
        key=lambda c: (
            0 if c["level"] == "empty" else (1 if c["level"] == "low" else 2),
            -c["available"],
            c["product"].name.lower(),
        )
    )

    kpis = {
        "products": len(cards),
        "available": sum(c["available"] for c in cards),
        "sold": sum(c["sold"] for c in cards),
        "defective": sum(c["defective"] for c in cards),
        "low_or_empty": sum(1 for c in cards if c["level"] in ("low", "empty")),
    }
    return cards, kpis


def stock_module_kpis():
    """Solo los KPIs (para vistas que no muestran las cards, ej. importar)."""
    _, kpis = _stock_cards_and_kpis()
    return kpis


@staff_member_required
def stock_overview(request):
    """Resumen de stock: cards por producto, búsqueda live."""
    q = (request.GET.get("q") or "").strip()

    cards, kpis = _stock_cards_and_kpis()
    if q:
        needle = q.lower()
        cards = [c for c in cards if needle in c["product"].name.lower()]

    ctx = _admin_context(
        request,
        title="Stock — Resumen",
        cards=cards,
        stock_kpis=kpis,
        active_tab="resumen",
        q=q,
    )
    return render(request, "admin/stock/overview.html", ctx)


@staff_member_required
def stock_list(request):
    """Vista moderna de la lista de cuentas (reemplaza el changelist clásico)."""
    from catalog.models import Product, StockItem
    from django.core.paginator import Paginator
    from urllib.parse import urlencode

    status = (request.GET.get("status") or "all").strip()
    product_filter = (request.GET.get("product") or "").strip()
    q = (request.GET.get("q") or "").strip()

    qs = StockItem.objects.select_related("product", "plan").order_by("-created_at")

    valid_statuses = {s for s, _ in StockItem.Status.choices}
    if status in valid_statuses:
        qs = qs.filter(status=status)

    if product_filter.isdigit():
        qs = qs.filter(product_id=int(product_filter))

    if q:
        qs = qs.filter(
            Q(credentials__icontains=q)
            | Q(label__icontains=q)
        )

    base_qs = StockItem.objects.all()
    if product_filter.isdigit():
        base_qs = base_qs.filter(product_id=int(product_filter))
    counts_by_status = {
        row["status"]: row["c"]
        for row in base_qs.values("status").annotate(c=Count("id"))
    }
    total_count = sum(counts_by_status.values())
    status_options = [
        {"value": "all", "label": "Todos", "count": total_count},
        {"value": "available", "label": "Disponibles", "count": counts_by_status.get("available", 0)},
        {"value": "sold", "label": "Vendidas", "count": counts_by_status.get("sold", 0)},
        {"value": "reserved", "label": "Reservadas", "count": counts_by_status.get("reserved", 0)},
        {"value": "defective", "label": "Caídas", "count": counts_by_status.get("defective", 0)},
        {"value": "disabled", "label": "Deshabilitadas", "count": counts_by_status.get("disabled", 0)},
    ]

    products_in_use = (
        Product.objects.filter(stock_items__isnull=False)
        .distinct()
        .order_by("name")
    )

    paginator = Paginator(qs, 50)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)

    # Decoramos cada item con (cuenta, perfil, pin) parseados desde
    # `credentials` para mostrarlos en columnas separadas en la vista
    # moderna de "Stock — Cuentas".
    from orders.credentials import split_account_extras

    decorated_items = []
    for item in page_obj.object_list:
        account_text, profile, pin = split_account_extras(item.credentials or "")
        item.account_text = account_text
        item.profile_text = profile
        item.pin_text = pin
        decorated_items.append(item)

    def _qs_for(page: int) -> str:
        params = {}
        if status and status != "all":
            params["status"] = status
        if product_filter:
            params["product"] = product_filter
        if q:
            params["q"] = q
        params["page"] = page
        return urlencode(params)

    ctx = _admin_context(
        request,
        title="Stock — Cuentas",
        items=decorated_items,
        page_obj=page_obj,
        paginator=paginator,
        querystring_prev=_qs_for(page_obj.previous_page_number()) if page_obj.has_previous() else "",
        querystring_next=_qs_for(page_obj.next_page_number()) if page_obj.has_next() else "",
        status=status,
        status_options=status_options,
        product_filter=product_filter,
        product_options=products_in_use,
        q=q,
        stock_kpis=stock_module_kpis(),
        active_tab="cuentas",
    )

    if request.headers.get("HX-Request"):
        return render(request, "admin/stock/_list_table.html", ctx)
    return render(request, "admin/stock/list.html", ctx)


@staff_member_required
@require_POST
def stock_quick_add(request):
    """Agrega varias cuentas a un producto desde el modal en stock_overview.

    Recibe POST con: product_id, plan_id (opcional), pasted (texto multilínea).
    Reusa el parser de StockItemAdmin._process_file.
    """
    from catalog.admin import StockItemAdmin
    from catalog.models import Product, Plan, StockItem
    from django.contrib.admin.sites import site as admin_site

    product_id = request.POST.get("product_id")
    plan_id = request.POST.get("plan_id") or None
    pasted = (request.POST.get("pasted") or "").strip()

    if not product_id or not pasted:
        messages.error(request, "Falta el producto o las credenciales pegadas.")
        return redirect("admin_stock_overview")

    product = get_object_or_404(Product, pk=product_id)
    plan = None
    if plan_id:
        plan = get_object_or_404(Plan, pk=plan_id, product=product)

    admin_obj = StockItemAdmin(StockItem, admin_site)
    try:
        created, skipped = admin_obj._process_file_with_stats(
            pasted, product=product, plan=plan,
        )
    except Exception as exc:  # pragma: no cover - defensive
        messages.error(request, f"Error procesando: {exc}")
        return redirect("admin_stock_overview")

    if created:
        msg = f"Se agregaron {created} cuenta(s) a {product.name}."
        if skipped:
            msg += f" Se omitieron {skipped} duplicado(s)."
        messages.success(request, msg)
    elif skipped:
        messages.warning(
            request,
            f"Todas las cuentas pegadas ({skipped}) ya existían en el stock. "
            "No se creó nada nuevo.",
        )
    else:
        messages.warning(
            request,
            "No se detectó ninguna cuenta válida. Revisa el formato.",
        )
    return redirect("admin_stock_overview")


@staff_member_required
@require_POST
def stock_quick_action(request, item_id: int):
    """Acciones rápidas sobre un StockItem (mark_defective / duplicate / disable)."""
    from catalog.models import StockItem

    action = request.POST.get("action", "")
    item = get_object_or_404(StockItem, pk=item_id)
    next_url = request.POST.get("next") or reverse("admin_stock_overview")

    if action == "mark_defective":
        item.status = StockItem.Status.DEFECTIVE
        item.save(update_fields=["status"])
        messages.success(request, f"Stock #{item.pk} marcado como caída.")
    elif action == "mark_available":
        item.status = StockItem.Status.AVAILABLE
        item.save(update_fields=["status"])
        messages.success(request, f"Stock #{item.pk} marcado como disponible.")
    elif action == "duplicate":
        clone = StockItem.objects.create(
            product=item.product,
            plan=item.plan,
            credentials=item.credentials,
            label=item.label,
            status=StockItem.Status.AVAILABLE,
        )
        messages.success(request, f"Stock duplicado: nuevo #{clone.pk}.")
    else:
        messages.error(request, f"Acción desconocida: {action}")

    return redirect(next_url)


# ---------------------------------------------------------------------------
# Customer 360° (Pack-F)
# ---------------------------------------------------------------------------

@staff_member_required
def customer_index(request):
    """Listado de clientes (por email único) ordenados por gasto total.

    Es el punto de entrada a la vista 360°. Combina pedidos pagados con
    su cliente derivado del email (o del FK user si está vinculado).
    """
    from orders.models import Order

    paid_statuses = (
        Order.Status.PAID, Order.Status.PREPARING, Order.Status.DELIVERED,
    )
    q = (request.GET.get("q") or "").strip()

    rows = (
        Order.objects.exclude(email="")
        .values("email")
        .annotate(
            orders_count=Count("id"),
            spent=Sum("total", filter=Q(status__in=paid_statuses)),
            last_at=Max("created_at"),
        )
        .order_by("-spent", "-last_at")
    )
    if q:
        rows = rows.filter(email__icontains=q)
    rows = list(rows[:200])

    for r in rows:
        r["spent"] = r["spent"] or Decimal("0")

    ctx = _admin_context(
        request,
        title="Clientes 360°",
        customers=rows,
        q=q,
    )
    return render(request, "admin/customer_index.html", ctx)


@staff_member_required
def customer_detail(request, email: str):
    """Vista 360° del cliente: timeline + stats + acciones rápidas."""
    from catalog.models import ProductReview
    from orders.models import Order, EmailLog
    from support.models import Ticket

    paid_statuses = (
        Order.Status.PAID, Order.Status.PREPARING, Order.Status.DELIVERED,
    )

    email = (email or "").strip().lower()
    if not email:
        messages.error(request, "Email vacío.")
        return redirect("admin_customer_index")

    orders = (
        Order.objects.filter(email__iexact=email)
        .order_by("-created_at")
        .prefetch_related("items__product", "items__plan")
    )
    if not orders.exists():
        messages.warning(request, f"No encontramos pedidos con el email {email}.")
        return redirect("admin_customer_index")

    # Ticket no tiene campo email — se busca por user.email del FK.
    tickets = (
        Ticket.objects.filter(user__email__iexact=email)
        .select_related("user", "order")
        .order_by("-created_at")
    )
    reviews = ProductReview.objects.filter(email__iexact=email).order_by("-created_at")
    emails_log = EmailLog.objects.filter(to_email__iexact=email).order_by("-sent_at")[:50]

    # Stats
    paid_orders = orders.filter(status__in=paid_statuses)
    total_spent = paid_orders.aggregate(s=Sum("total"))["s"] or Decimal("0")
    orders_count = orders.count()
    delivered_count = orders.filter(status=Order.Status.DELIVERED).count()
    last_order = orders.first()
    last_paid_at = paid_orders.aggregate(m=Max("paid_at"))["m"]
    days_since = (
        (timezone.now() - last_paid_at).days if last_paid_at else None
    )

    # Producto favorito (más comprado)
    fav = (
        Order.objects.filter(email__iexact=email, items__product__isnull=False)
        .values("items__product__name")
        .annotate(c=Count("items"))
        .order_by("-c")
        .first()
    )
    favorite_product = fav["items__product__name"] if fav else None

    # Datos de contacto agregados (último pedido manda)
    first_name = ""
    phone = ""
    user_id = None
    if last_order:
        phone = last_order.phone or ""
        if last_order.user:
            user_id = last_order.user_id
            first_name = last_order.user.first_name or last_order.user.username

    # Timeline unificada
    timeline = []
    for o in orders:
        timeline.append({
            "kind": "order",
            "icon": "shopping_bag",
            "color": _ORDER_COLORS.get(o.status, "#94a3b8"),
            "when": o.created_at,
            "title": f"Pedido #{o.short_uuid} — {o.get_status_display()}",
            "detail": f"{o.currency} {o.total} · {o.channel}",
            "link": reverse("admin:orders_order_change", args=[o.pk]),
        })
    for t in tickets:
        timeline.append({
            "kind": "ticket",
            "icon": "support_agent",
            "color": "#06b6d4",
            "when": t.created_at,
            "title": f"Ticket: {t.subject}",
            "detail": t.get_status_display() if hasattr(t, "get_status_display") else "",
            "link": reverse("admin:support_ticket_change", args=[t.pk]),
        })
    for r in reviews:
        timeline.append({
            "kind": "review",
            "icon": "star",
            "color": "#f59e0b",
            "when": r.created_at,
            "title": f"Reseña ({r.rating}★) — {r.product.name}",
            "detail": (r.body or "")[:120],
            "link": reverse("admin:catalog_productreview_change", args=[r.pk]),
        })
    for e in emails_log:
        timeline.append({
            "kind": "email",
            "icon": "mail",
            "color": "#a78bfa",
            "when": e.sent_at,
            "title": f"Correo: {e.subject}",
            "detail": e.get_kind_display() if hasattr(e, "get_kind_display") else e.kind,
            "link": reverse("admin:orders_emaillog_change", args=[e.pk]),
        })
    timeline.sort(key=lambda x: x["when"], reverse=True)

    whatsapp_url = ""
    if phone:
        clean = "".join(ch for ch in phone if ch.isdigit())
        if clean:
            from urllib.parse import quote
            msg = quote(f"Hola! Te escribimos de Jheliz. Vimos tu compra y queremos saber cómo te ha ido.")
            whatsapp_url = f"https://wa.me/{clean}?text={msg}"

    ctx = _admin_context(
        request,
        title=f"Cliente 360° — {email}",
        customer_email=email,
        customer_first_name=first_name,
        customer_phone=phone,
        customer_user_id=user_id,
        whatsapp_url=whatsapp_url,
        total_spent=total_spent,
        orders_count=orders_count,
        delivered_count=delivered_count,
        last_paid_at=last_paid_at,
        days_since=days_since,
        favorite_product=favorite_product,
        orders=orders,
        tickets=tickets,
        reviews=reviews,
        emails_log=emails_log,
        timeline=timeline,
        last_order=last_order,
    )
    return render(request, "admin/customer_360.html", ctx)


_ORDER_COLORS = {
    "pending":   "#f59e0b",
    "verifying": "#f97316",
    "paid":      "#22d3ee",
    "preparing": "#a78bfa",
    "delivered": "#10b981",
    "cancelled": "#ef4444",
    "refunded":  "#94a3b8",
}


# ---------------------------------------------------------------------------
# Support chat (admin side) — vista tipo chat para responder tickets
# ---------------------------------------------------------------------------

def _ticket_template_vars(ticket) -> dict:
    """Dict con las variables que sustituye ReplyTemplate.render para este ticket."""
    user = ticket.user
    order = ticket.order
    nombre = ""
    if user:
        nombre = user.get_full_name() or user.username or ""
    pedido = ""
    telefono = ""
    producto = ""
    if order:
        pedido = order.short_uuid if hasattr(order, "short_uuid") else str(order.pk)
        telefono = getattr(order, "phone", "") or ""
        first_item = order.items.first() if hasattr(order, "items") else None
        if first_item:
            producto = getattr(first_item, "product_name", "") or ""
    return {
        "nombre": nombre,
        "pedido": pedido,
        "producto": producto,
        "telefono": telefono,
        "fecha": timezone.localdate().strftime("%d/%m/%Y"),
    }


@staff_member_required
def support_chat_view(request, ticket_id: int):
    """Chat dentro del admin para responder un ticket en formato burbujas."""
    from support.models import ReplyTemplate, Ticket

    ticket = get_object_or_404(
        Ticket.objects.select_related("user", "order"),
        pk=ticket_id,
    )
    templates = ReplyTemplate.objects.filter(is_active=True).order_by("category", "name")
    ctx = _admin_context(
        request,
        ticket=ticket,
        messages_thread=ticket.messages.all(),
        messages_poll_url=reverse("admin_support_chat_messages", args=[ticket.pk]),
        reply_templates=templates,
        chat_vars=_ticket_template_vars(ticket),
        title=f"Chat — Ticket #{ticket.pk}",
    )
    return render(request, "admin/support/chat.html", ctx)


@staff_member_required
@require_POST
def support_chat_reply(request, ticket_id: int):
    """Crea un TicketMessage del staff. HTMX-aware: devuelve el partial."""
    from support.models import ReplyTemplate, Ticket, TicketMessage

    ticket = get_object_or_404(Ticket, pk=ticket_id)
    body = (request.POST.get("body") or "").strip()
    template_id = request.POST.get("template_id") or ""
    if template_id.isdigit():
        tpl = ReplyTemplate.objects.filter(pk=int(template_id), is_active=True).first()
        if tpl and not body:
            body = tpl.render(ticket=ticket)
        if tpl:
            tpl.use_count = F("use_count") + 1
            tpl.last_used_at = timezone.now()
            tpl.save(update_fields=["use_count", "last_used_at"])

    if not body:
        if request.headers.get("HX-Request"):
            return HttpResponse(status=400)
        messages.error(request, "El mensaje no puede estar vacío.")
        return redirect("admin_support_chat", ticket_id=ticket.pk)

    TicketMessage.objects.create(
        ticket=ticket, author=request.user, body=body, is_from_staff=True,
    )
    ticket.status = Ticket.Status.PENDING_USER
    ticket.save(update_fields=["status", "updated_at"])

    if request.headers.get("HX-Request"):
        return render(
            request,
            "support/_messages.html",
            {
                "ticket": ticket,
                "messages_thread": ticket.messages.all(),
                "messages_poll_url": reverse(
                    "admin_support_chat_messages", args=[ticket.pk]
                ),
            },
        )
    messages.success(request, "Respuesta enviada al cliente.")
    return redirect("admin_support_chat", ticket_id=ticket.pk)


@staff_member_required
def support_chat_messages(request, ticket_id: int):
    """HTMX poll endpoint del admin: devuelve solo el partial."""
    from support.models import Ticket

    ticket = get_object_or_404(Ticket, pk=ticket_id)
    return render(
        request,
        "support/_messages.html",
        {
            "ticket": ticket,
            "messages_thread": ticket.messages.all(),
            "messages_poll_url": reverse(
                "admin_support_chat_messages", args=[ticket.pk]
            ),
        },
    )


# ---------------------------------------------------------------------------
# Reemplazar cuenta bloqueada (búsqueda por correo) (#extra)
# ---------------------------------------------------------------------------

@staff_member_required
def replace_blocked_account_view(request):
    """Pantalla dedicada: pego el correo viejo, veo todos los items que lo
    están usando, marco los afectados y los mando a la pantalla de reemplazo
    masivo existente.
    """
    from catalog.models import Product
    from orders.models import OrderItem
    from orders import credentials as creds_utils

    email_query = (request.GET.get("email") or request.POST.get("email") or "").strip()
    product_id = request.GET.get("product") or request.POST.get("product") or ""

    matches = []
    searched = False
    if email_query:
        searched = True
        target = email_query.casefold()
        # Solo items entregados con credenciales no vacías y, si está,
        # vencimiento futuro (no listamos cuentas que ya expiraron hace tiempo).
        qs = (
            OrderItem.objects
            .filter(delivered_credentials__isnull=False)
            .exclude(delivered_credentials="")
            .select_related("order", "order__user", "product", "plan")
            .order_by("-order__created_at")
        )
        if product_id:
            try:
                qs = qs.filter(product_id=int(product_id))
            except (TypeError, ValueError):
                pass
        for item in qs.iterator():
            parsed = creds_utils.parse(item.delivered_credentials)
            if parsed.email and parsed.email.casefold() == target:
                user = item.order.user
                is_distributor = bool(user and getattr(user, "is_distributor", False))
                matches.append({
                    "item": item,
                    "user": user,
                    "is_distributor": is_distributor,
                    "role_label": "Distribuidor" if is_distributor else "Cliente",
                    "current_password": parsed.password,
                })

    if request.method == "POST" and request.POST.get("action") == "go_replace":
        ids = request.POST.getlist("ids")
        if ids:
            url = reverse("admin:orders_orderitem_replace_account")
            qs_str = "&".join(f"ids={pk}" for pk in ids)
            return redirect(f"{url}?{qs_str}")
        messages.warning(request, "Marcá al menos un item para continuar.")

    products = Product.objects.filter(is_active=True).order_by("name")
    selected_product_id = ""
    try:
        selected_product_id = str(int(product_id)) if product_id else ""
    except (TypeError, ValueError):
        selected_product_id = ""

    ctx = _admin_context(
        request,
        title="Reemplazar cuenta bloqueada",
        email_query=email_query,
        searched=searched,
        matches=matches,
        products=products,
        selected_product_id=selected_product_id,
    )
    return render(request, "admin/replace_blocked_account.html", ctx)
