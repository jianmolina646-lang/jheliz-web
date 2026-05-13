"""Vistas auxiliares del panel admin: reportes, clientes valiosos, health check
y endpoint de notificaciones para polling.

Se montan bajo `/panel-jheliz-2026/...` antes del catch-all `admin.site.urls` para
que Django las matchee primero.
"""

from __future__ import annotations

import csv
import json
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
    de resultados HTML (`/panel-jheliz-2026/search/?q=...&full=1`).
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
    from livechat.models import ChatMessage, ChatRoom
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

    # Chat en vivo: salas con mensajes del cliente que el admin no ha visto.
    chat_rooms_unread = (
        ChatRoom.objects.filter(status=ChatRoom.Status.OPEN)
        .order_by("-last_message_at")[:item_limit]
    )
    chat_unread_total = 0
    for room in chat_rooms_unread:
        msg_qs = ChatMessage.objects.filter(
            room_id=room.pk, sender=ChatMessage.Sender.CUSTOMER,
        )
        if room.last_admin_seen_at:
            msg_qs = msg_qs.filter(created_at__gt=room.last_admin_seen_at)
        unread_count = msg_qs.count()
        if unread_count == 0:
            continue
        chat_unread_total += unread_count
        ts = room.last_message_at or room.created_at
        last_msg = ChatMessage.objects.filter(room_id=room.pk).order_by("-created_at").first()
        snippet = (last_msg.body if last_msg else "")[:80]
        items.append({
            "id": f"livechat-{room.pk}",
            "kind": "livechat",
            "icon": "chat",
            "title": f"Chat con {room.display_name} · {unread_count} sin leer",
            "subtitle": snippet or "(mensaje vacío)",
            "url": reverse("admin_livechat_detail", args=[room.pk]),
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
        "livechat_unread": chat_unread_total,
    }
    counts["total"] = (
        counts["verifying"] + counts["preparing"]
        + counts["open_tickets"] + counts["livechat_unread"]
    )

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
    a renovar con 1 click (magic link).
    """
    import urllib.parse
    from django.conf import settings as dj_settings

    phone = (item.order.phone or "").strip().replace(" ", "").replace("+", "")
    if not phone:
        return ""
    if not phone.startswith("51") and len(phone) == 9:
        phone = "51" + phone
    fecha = item.expires_at.strftime("%d/%m/%Y") if item.expires_at else ""

    site_url = getattr(dj_settings, "SITE_URL", "").rstrip("/")
    renew_link = (
        f"{site_url}/renovar/t/{item.renewal_token}/"
        if item.renewal_token else ""
    )
    txt_lines = [
        f"Hola! Te recordamos que tu *{item.product_name} ({item.plan_name})* "
        f"vence el {fecha}.",
    ]
    if renew_link:
        txt_lines.append(f"Renueva con 1 click aquí 👉 {renew_link}")
    else:
        txt_lines.append("¿Quieres renovarlo? Te paso el link de pago.")
    txt = "\n\n".join(txt_lines)
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
    # ``redirect_to`` permite que el modal viva en /cuentas/ y vuelva ahí
    # en vez de tirar siempre al overview clásico.
    fallback_url = request.POST.get("redirect_to") or reverse("admin_stock_overview")

    if not product_id or not pasted:
        messages.error(request, "Falta el producto o las credenciales pegadas.")
        return redirect(fallback_url)

    product = get_object_or_404(Product, pk=product_id)
    plan = None
    if plan_id:
        plan = get_object_or_404(Plan, pk=plan_id, product=product)

    # Cross-platform duplicate check ANTES de procesar: avisa si alguno
    # de los correos ya está cargado en OTRO producto (vendido o no).
    # Esto es lo que pidió el usuario: "no subir correos que ya están
    # vendidos".
    import re as _re
    new_emails = {
        m.lower() for m in _re.findall(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", pasted
        )
    }
    cross_hits = []
    if new_emails:
        # Pre-filtramos por icontains en SQL para no traer todo el stock.
        q_or = Q()
        for em in new_emails:
            q_or |= Q(credentials__icontains=em)
        candidates = (
            StockItem.objects.exclude(product=product)
            .filter(q_or)
            .select_related("product")
        )
        for item in candidates:
            text_lc = (item.credentials or "").lower()
            for em in new_emails:
                if em in text_lc:
                    cross_hits.append((em, item.product.name, item.get_status_display()))
                    break

    admin_obj = StockItemAdmin(StockItem, admin_site)
    try:
        created, skipped = admin_obj._process_file_with_stats(
            pasted, product=product, plan=plan,
        )
    except Exception as exc:  # pragma: no cover - defensive
        messages.error(request, f"Error procesando: {exc}")
        return redirect(fallback_url)

    if created:
        msg = f"Se agregaron {created} cuenta(s) a {product.name}."
        if skipped:
            msg += f" Se omitieron {skipped} duplicado(s) dentro de {product.name}."
        messages.success(request, msg)
    elif skipped:
        messages.warning(
            request,
            f"Todas las cuentas pegadas ({skipped}) ya existían en {product.name}. "
            "No se creó nada nuevo.",
        )
    else:
        messages.warning(
            request,
            "No se detectó ninguna cuenta válida. Revisa el formato.",
        )

    if cross_hits:
        # De-dup y armado de mensaje en una línea por correo conflictivo.
        seen = set()
        unique = []
        for em, pname, status in cross_hits:
            key = (em, pname)
            if key in seen:
                continue
            seen.add(key)
            unique.append((em, pname, status))
        lines = "; ".join(f"{em} ya está en {pname} ({status})" for em, pname, status in unique[:5])
        suffix = "" if len(unique) <= 5 else f" (+{len(unique) - 5} más)"
        messages.warning(
            request,
            "⚠️ Detectamos cuentas que ya existen en OTRAS plataformas: "
            + lines + suffix + ". Revisalas — si se trata de un re-uso intencional, ignorá este aviso.",
        )

    return redirect(fallback_url)


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
    elif action == "mark_sold":
        # Marca manual: para casos en que se vendió fuera del checkout
        # automático (ej. venta directa por WhatsApp) y querés que quede
        # registrado para no re-cargar el mismo correo.
        item.status = StockItem.Status.SOLD
        update_fields = ["status"]
        if not item.sold_at:
            item.sold_at = timezone.now()
            update_fields.append("sold_at")
        item.save(update_fields=update_fields)
        messages.success(request, f"Stock #{item.pk} marcado como vendida.")
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
# Control de cuentas — vista agrupada por plataforma (sustituye al Excel/bloc)
# ---------------------------------------------------------------------------

def _extract_primary_email(text: str) -> str:
    """Devuelve el primer email (lowercase) encontrado en el texto, o ''."""
    import re
    if not text:
        return ""
    matches = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return matches[0].lower() if matches else ""


def _strip_password_from_account_line(text: str) -> str:
    """Devuelve solo la línea con el correo (no expone contraseña en la vista).

    Si el texto tiene formato ``Correo: x@y.com\\nContraseña: secreto``,
    devuelve solo ``x@y.com``. Si es ``x@y.com:secreto`` también filtra.
    """
    email = _extract_primary_email(text or "")
    return email or (text or "").splitlines()[0][:80]


@staff_member_required
def cuentas_dashboard(request):
    """Control de cuentas: muestra TODAS las cuentas agrupadas por plataforma.

    Es la sección "📚 Control de cuentas" del sidebar. Pensada para reemplazar
    el Excel / bloc de notas del usuario: ver de un vistazo cuántas cuentas
    quedan disponibles y cuáles ya están vendidas por plataforma.
    """
    from catalog.models import Product, StockItem
    from orders.credentials import split_account_extras

    q = (request.GET.get("q") or "").strip().lower()
    status_filter = (request.GET.get("status") or "all").strip()
    show_only = (request.GET.get("only") or "").strip()  # "active" = oculta deshabilitadas

    valid_statuses = {s for s, _ in StockItem.Status.choices}

    qs = StockItem.objects.select_related("product", "plan").order_by("-created_at")
    if status_filter in valid_statuses:
        qs = qs.filter(status=status_filter)

    # Búsqueda cross-plataforma: si pegás un correo te muestra dónde está.
    matched_email = ""
    if q:
        qs = qs.filter(credentials__icontains=q)
        # Detectar si q "parece" un email para resaltarlo en el header.
        if "@" in q:
            matched_email = q

    # Cargamos todo (no hay millones de cuentas — es una tienda).
    items = list(qs[:5000])

    # Decoramos con cuenta/perfil/pin parseados.
    for it in items:
        account, profile, pin = split_account_extras(it.credentials or "")
        it.account_text = account
        it.profile_text = profile
        it.pin_text = pin
        it.email_lc = _extract_primary_email(account)

    # Agrupar por producto. Productos sin items y sin filtro aplicado los
    # mostramos también con sección vacía (para que el usuario sepa que la
    # plataforma existe y pueda agregar cuentas).
    products_with_items: dict[int, dict] = {}
    for it in items:
        slot = products_with_items.setdefault(
            it.product_id,
            {
                "product": it.product,
                "items": [],
                "available": 0, "sold": 0, "reserved": 0,
                "defective": 0, "disabled": 0, "total": 0,
            },
        )
        slot["items"].append(it)
        slot[it.status] = slot.get(it.status, 0) + 1
        slot["total"] += 1

    # Si no hay filtros, agregar productos sin stock también (sección vacía).
    if not q and status_filter == "all":
        active_products = Product.objects.filter(is_active=True).only("id", "name")
        for p in active_products:
            if p.pk not in products_with_items:
                products_with_items[p.pk] = {
                    "product": p,
                    "items": [],
                    "available": 0, "sold": 0, "reserved": 0,
                    "defective": 0, "disabled": 0, "total": 0,
                }

    # Ordenar: primero las plataformas con cuentas disponibles (orden alfabético).
    groups = sorted(
        products_with_items.values(),
        key=lambda g: (
            0 if g["available"] > 0 else (1 if g["total"] > 0 else 2),
            g["product"].name.lower(),
        ),
    )

    # KPIs globales (todas las plataformas).
    all_counts = (
        StockItem.objects.values("status")
        .annotate(c=Count("id"))
    )
    counts_by_status = {row["status"]: row["c"] for row in all_counts}
    kpis = {
        "available": counts_by_status.get("available", 0),
        "sold": counts_by_status.get("sold", 0),
        "defective": counts_by_status.get("defective", 0),
        "reserved": counts_by_status.get("reserved", 0),
        "disabled": counts_by_status.get("disabled", 0),
        "total": sum(counts_by_status.values()),
        "platforms": len(products_with_items),
    }

    status_options = [
        {"value": "all", "label": "Todas", "count": kpis["total"]},
        {"value": "available", "label": "Disponibles", "count": kpis["available"]},
        {"value": "sold", "label": "Vendidas", "count": kpis["sold"]},
        {"value": "reserved", "label": "Reservadas", "count": kpis["reserved"]},
        {"value": "defective", "label": "Caídas", "count": kpis["defective"]},
        {"value": "disabled", "label": "Deshabilitadas", "count": kpis["disabled"]},
    ]

    ctx = _admin_context(
        request,
        title="Control de cuentas",
        groups=groups,
        kpis=kpis,
        status_options=status_options,
        status=status_filter,
        q=q,
        matched_email=matched_email,
        show_only=show_only,
        total_results=len(items),
    )
    return render(request, "admin/cuentas/dashboard.html", ctx)


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
            "detail": (r.comment or "")[:120],
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


# ---------------------------------------------------------------------------
# Bandeja "Necesita acción" — feed unificado
#
# A diferencia del dashboard (que muestra contadores agregados por categoría),
# la bandeja lista TODAS las cosas que necesitan acción del admin en una sola
# tabla cronológica con razón + prioridad + link directo.
# ---------------------------------------------------------------------------

_INBOX_PRIORITY = {"red": 0, "orange": 1, "yellow": 2, "blue": 3}


def _inbox_collect_items():
    """Devuelve la lista unificada de items que requieren acción.

    Cada item es un dict con: kind, label, reason, link, age_seconds, priority,
    icon, ref (texto corto para identificarlo).
    """
    from orders.models import Order, OrderItem
    from support.models import Ticket
    from catalog.models import ProductReview, StockItem
    from accounts.models import User

    now = timezone.now()
    items = []

    def _age_seconds(dt):
        if not dt:
            return 0
        return max(0, int((now - dt).total_seconds()))

    # 1) Pedidos con comprobante Yape sin verificar.
    for o in (
        Order.objects.filter(status=Order.Status.VERIFYING)
        .order_by("-payment_proof_uploaded_at", "-created_at")[:50]
    ):
        items.append({
            "kind": "yape_proof",
            "label": "Comprobante Yape pendiente",
            "reason": "Subió comprobante. Revisá si el monto y la referencia coinciden.",
            "ref": f"#{o.short_uuid} — {o.email or o.phone or 'sin contacto'}",
            "link": reverse("admin:orders_order_change", args=[o.pk]),
            "icon": "qr_code_scanner",
            "priority": "orange",
            "age_seconds": _age_seconds(o.payment_proof_uploaded_at or o.created_at),
            "money": float(o.total or 0),
        })

    # 2) Pedidos en preparación con items sin credenciales/stock vinculado
    #    (esto NO incluye los YA entregados). Son los pedidos atascados.
    waiting_qs = (
        Order.objects.filter(status=Order.Status.PREPARING)
        .filter(
            Q(items__delivered_credentials="") & Q(items__stock_item__isnull=True)
        )
        .distinct()
        .order_by("-paid_at")[:50]
    )
    for o in waiting_qs:
        items.append({
            "kind": "waiting_stock",
            "label": "Pedido sin entregar",
            "reason": "Pagó hace rato pero no se le entregaron credenciales aún.",
            "ref": f"#{o.short_uuid} — {o.email or o.phone or 'sin contacto'}",
            "link": reverse("admin:orders_order_change", args=[o.pk]),
            "icon": "inventory_2",
            "priority": "red",
            "age_seconds": _age_seconds(o.paid_at or o.created_at),
            "money": float(o.total or 0),
        })

    # 3) Tickets de soporte sin responder.
    for t in (
        Ticket.objects.filter(
            status__in=[Ticket.Status.OPEN, Ticket.Status.PENDING_ADMIN]
        )
        .select_related("order")
        .order_by("-updated_at")[:50]
    ):
        order_ref = ""
        if t.order_id:
            order_ref = f" (pedido #{t.order.short_uuid})"
        items.append({
            "kind": "ticket",
            "label": "Ticket sin responder",
            "reason": (t.subject or "Soporte: cliente esperando respuesta.")[:140],
            "ref": f"{t.email or 'anónimo'}{order_ref}",
            "link": reverse("admin:support_ticket_change", args=[t.pk]),
            "icon": "support_agent",
            "priority": "blue",
            "age_seconds": _age_seconds(t.updated_at or t.created_at),
            "money": 0.0,
        })

    # 4) Reseñas pendientes de moderación.
    for r in (
        ProductReview.objects.filter(status=ProductReview.Status.PENDING)
        .select_related("product")
        .order_by("-created_at")[:30]
    ):
        items.append({
            "kind": "review",
            "label": "Reseña pendiente",
            "reason": (r.comment or "Sin comentario.")[:140],
            "ref": f"{r.product.name if r.product else '—'} — {r.author or 'anónimo'}",
            "link": reverse(
                "admin:catalog_productreview_change", args=[r.pk]
            ),
            "icon": "rate_review",
            "priority": "blue",
            "age_seconds": _age_seconds(r.created_at),
            "money": 0.0,
        })

    # 5) Distribuidores por aprobar.
    for u in (
        User.objects.filter(role="distribuidor", distributor_approved=False)
        .order_by("-date_joined")[:30]
    ):
        items.append({
            "kind": "distributor",
            "label": "Distribuidor por aprobar",
            "reason": "Solicitó cuenta de distribuidor. Validalo y aprobá.",
            "ref": f"{u.email or u.username}",
            "link": reverse("admin:accounts_user_change", args=[u.pk]),
            "icon": "verified_user",
            "priority": "yellow",
            "age_seconds": _age_seconds(u.date_joined),
            "money": 0.0,
        })

    # 6) Stock que vence en proveedor en ≤3 días (rotar antes de que afecte clientes).
    for s in (
        StockItem.objects
        .filter(
            status__in=[
                StockItem.Status.AVAILABLE,
                StockItem.Status.RESERVED,
                StockItem.Status.SOLD,
            ],
            provider_expires_at__isnull=False,
            provider_expires_at__lte=now + timedelta(days=3),
            provider_expires_at__gt=now - timedelta(days=1),
        )
        .select_related("product")
        .order_by("provider_expires_at")[:30]
    ):
        days_left = (s.provider_expires_at - now).days
        items.append({
            "kind": "stock_expiring",
            "label": "Cuenta vence en proveedor",
            "reason": (
                f"La cuenta original muere en {days_left}d. "
                "Reponela antes de que afecte clientes."
            ),
            "ref": f"{s.product.name} — stock #{s.pk}",
            "link": reverse("admin:catalog_stockitem_change", args=[s.pk]),
            "icon": "warning_amber",
            "priority": "orange" if days_left > 0 else "red",
            "age_seconds": 0,
            "money": 0.0,
        })

    # 7) Items de pedidos vencidos hoy o que vencen hoy (renovación urgente).
    expiring_today_items = (
        OrderItem.objects.filter(
            expires_at__date=now.date(),
            order__status__in=(
                Order.Status.PAID,
                Order.Status.PREPARING,
                Order.Status.DELIVERED,
            ),
        )
        .select_related("order", "product", "plan")
        .order_by("expires_at")[:30]
    )
    for it in expiring_today_items:
        items.append({
            "kind": "renewal_today",
            "label": "Cuenta vence hoy",
            "reason": "Cliente puede renovar ahora con magic link. Mandale recordatorio.",
            "ref": (
                f"#{it.order.short_uuid} — {it.product_name} — "
                f"{it.order.email or it.order.phone or 'sin contacto'}"
            ),
            "link": reverse("admin_renewals") + "?w=today",
            "icon": "schedule",
            "priority": "yellow",
            "age_seconds": 0,
            "money": 0.0,
        })

    # 8) Items reportados como caídos por distribuidores.
    for it in (
        OrderItem.objects.filter(reported_broken_at__isnull=False)
        .filter(order__status__in=(
            Order.Status.PAID, Order.Status.PREPARING, Order.Status.DELIVERED,
        ))
        .select_related("order", "product")
        .order_by("-reported_broken_at")[:30]
    ):
        items.append({
            "kind": "reported_broken",
            "label": "Cuenta reportada caída",
            "reason": (
                it.reported_broken_note or
                "Distribuidor reporta que la cuenta dejó de funcionar."
            )[:140],
            "ref": (
                f"#{it.order.short_uuid} — {it.product_name} — "
                f"{it.order.email or 'sin contacto'}"
            ),
            "link": reverse("admin:orders_order_change", args=[it.order_id]),
            "icon": "report",
            "priority": "red",
            "age_seconds": _age_seconds(it.reported_broken_at),
            "money": 0.0,
        })

    return items


@staff_member_required
def inbox_view(request):
    """Bandeja unificada de cosas que necesitan acción (single feed)."""
    kind_filter = (request.GET.get("kind") or "").strip()
    sort = (request.GET.get("sort") or "priority").strip()

    items = _inbox_collect_items()

    # Stats por tipo (para los chips/filtros arriba).
    stats = {}
    for it in items:
        stats[it["kind"]] = stats.get(it["kind"], 0) + 1

    if kind_filter and kind_filter != "all":
        items = [it for it in items if it["kind"] == kind_filter]

    if sort == "age":
        items.sort(key=lambda it: -it["age_seconds"])
    else:  # priority (red → orange → yellow → blue), luego por edad desc
        items.sort(
            key=lambda it: (
                _INBOX_PRIORITY.get(it["priority"], 99),
                -it["age_seconds"],
            )
        )

    # Tone classes para Tailwind compilado por Unfold.
    tone = {
        "red": "border-red-500 bg-red-500/10 text-red-100",
        "orange": "border-orange-500 bg-orange-500/10 text-orange-100",
        "yellow": "border-yellow-500 bg-yellow-500/10 text-yellow-100",
        "blue": "border-blue-500 bg-blue-500/10 text-blue-100",
    }
    for it in items:
        it["classes"] = tone.get(it["priority"], tone["blue"])
        # Friendly age string.
        sec = it["age_seconds"]
        if sec <= 0:
            it["age_label"] = "ahora"
        elif sec < 3600:
            it["age_label"] = f"hace {sec // 60} min"
        elif sec < 86400:
            it["age_label"] = f"hace {sec // 3600} h"
        else:
            it["age_label"] = f"hace {sec // 86400} d"

    # Lista de chips (tipos disponibles + total).
    chips = [
        ("all", "Todo", sum(stats.values()), "list"),
        ("yape_proof", "Yape", stats.get("yape_proof", 0), "qr_code_scanner"),
        ("waiting_stock", "Sin entregar", stats.get("waiting_stock", 0), "inventory_2"),
        ("ticket", "Tickets", stats.get("ticket", 0), "support_agent"),
        ("review", "Reseñas", stats.get("review", 0), "rate_review"),
        ("distributor", "Distribuidores", stats.get("distributor", 0), "verified_user"),
        ("stock_expiring", "Stock por vencer", stats.get("stock_expiring", 0), "warning_amber"),
        ("renewal_today", "Vencen hoy", stats.get("renewal_today", 0), "schedule"),
        ("reported_broken", "Caídas reportadas", stats.get("reported_broken", 0), "report"),
    ]

    ctx = _admin_context(
        request,
        title="Bandeja — Necesita acción",
        items=items,
        chips=chips,
        kind_filter=kind_filter or "all",
        sort=sort,
        total=sum(stats.values()),
    )
    return render(request, "admin/inbox.html", ctx)


# ---------------------------------------------------------------------------
# Reportes financieros con gráficos (mensual + categorías + tendencia)
#
# Vista que extiende el reporte plano con:
#   - Gráfico de ventas mensuales (12 meses).
#   - Donut de revenue por categoría.
#   - Tendencia: este mes vs mes anterior (con %).
#   - Top 5 clientes por gasto del año.
# ---------------------------------------------------------------------------

@staff_member_required
def reports_charts_view(request):
    from orders.models import Order, OrderItem

    paid_statuses = (
        Order.Status.PAID, Order.Status.PREPARING, Order.Status.DELIVERED,
    )
    paid_qs = Order.objects.filter(status__in=paid_statuses)

    now = timezone.localtime()
    today = now.date()

    # ---- Ventas mensuales últimos 12 meses ---------------------------------
    # Construimos lista de los últimos 12 meses (desde hace 11 meses hasta este).
    months = []
    cursor = today.replace(day=1)
    for _ in range(12):
        months.append(cursor)
        # Retroceder 1 mes (sin importar duración).
        if cursor.month == 1:
            cursor = cursor.replace(year=cursor.year - 1, month=12)
        else:
            cursor = cursor.replace(month=cursor.month - 1)
    months.reverse()  # del más antiguo al más reciente

    month_buckets = {(m.year, m.month): Decimal("0") for m in months}
    month_orders = {(m.year, m.month): 0 for m in months}
    start_first_month = timezone.make_aware(
        datetime.combine(months[0], datetime.min.time())
    )
    for o in paid_qs.filter(paid_at__gte=start_first_month).only("paid_at", "total"):
        if not o.paid_at:
            continue
        local = timezone.localtime(o.paid_at)
        key = (local.year, local.month)
        if key in month_buckets:
            month_buckets[key] += o.total or Decimal("0")
            month_orders[key] += 1

    month_labels = [m.strftime("%b %y") for m in months]
    month_revenue = [float(month_buckets[(m.year, m.month)]) for m in months]
    month_count = [month_orders[(m.year, m.month)] for m in months]

    # ---- Tendencia este mes vs mes anterior --------------------------------
    this_revenue = month_revenue[-1] if month_revenue else 0.0
    prev_revenue = month_revenue[-2] if len(month_revenue) >= 2 else 0.0
    if prev_revenue > 0:
        trend_pct = (this_revenue - prev_revenue) / prev_revenue * 100
    elif this_revenue > 0:
        trend_pct = 100.0
    else:
        trend_pct = 0.0

    this_orders = month_count[-1] if month_count else 0
    prev_orders = month_count[-2] if len(month_count) >= 2 else 0

    # ---- Revenue por categoría (12 meses) ----------------------------------
    cat_rows = (
        OrderItem.objects
        .filter(
            order__status__in=paid_statuses,
            order__paid_at__gte=start_first_month,
        )
        .values("product__category__name")
        .annotate(
            revenue=Sum(F("unit_price") * F("quantity")),
            units=Sum("quantity"),
        )
        .order_by("-revenue")
    )
    cat_labels = []
    cat_data = []
    cat_units = []
    for r in cat_rows:
        cat_labels.append(r["product__category__name"] or "Sin categoría")
        cat_data.append(float(r["revenue"] or 0))
        cat_units.append(int(r["units"] or 0))

    # ---- Top 5 clientes (12 meses) ----------------------------------------
    top_customers = list(
        paid_qs.filter(paid_at__gte=start_first_month)
        .values("email")
        .annotate(
            spent=Sum("total"),
            orders=Count("id"),
        )
        .order_by("-spent")[:5]
    )

    # ---- Comparación interanual (Year-over-Year) --------------------------
    # Mismo mes hace 1 año vs ahora.
    one_year_ago_month = months[0]
    yoy_revenue = month_revenue[0] if month_revenue else 0.0
    if yoy_revenue > 0:
        yoy_pct = (this_revenue - yoy_revenue) / yoy_revenue * 100
    elif this_revenue > 0:
        yoy_pct = 100.0
    else:
        yoy_pct = 0.0

    ctx = _admin_context(
        request,
        title="Reportes con gráficos",
        currency_symbol=settings.DEFAULT_CURRENCY_SYMBOL,
        # Charts
        sales_chart_json=json.dumps({
            "labels": month_labels,
            "revenue": month_revenue,
            "orders": month_count,
        }),
        cat_chart_json=json.dumps({
            "labels": cat_labels,
            "data": cat_data,
        }),
        # KPIs
        this_revenue=this_revenue,
        prev_revenue=prev_revenue,
        trend_pct=trend_pct,
        this_orders=this_orders,
        prev_orders=prev_orders,
        yoy_revenue=yoy_revenue,
        yoy_pct=yoy_pct,
        yoy_label=one_year_ago_month.strftime("%b %y"),
        # Top customers
        top_customers=top_customers,
        # Categorías para tabla complementaria
        cat_rows=list(zip(cat_labels, cat_data, cat_units)),
    )
    return render(request, "admin/reports_charts.html", ctx)


# ---------------------------------------------------------------------------
# 2FA setup wizard (UX amigable)
#
# Hoy `django-otp` está instalado pero el setup pasa por el changelist de
# `TOTP devices` (clunky). Esta vista da:
#   - Estado actual (¿tiene 2FA configurado? ¿está enforced en este request?)
#   - QR + secret key visibles para escanear con Authenticator
#   - Verificación del código antes de confirmar
#   - Generación de 8 backup codes (django-otp StaticTokens)
#
# Si el flag ADMIN_2FA_ENFORCED=True, el admin ya pide TOTP en el login.
# Mientras está en False, esta vista permite preparar el dispositivo SIN
# riesgo de bloqueo.
# ---------------------------------------------------------------------------

@staff_member_required
def admin_2fa_setup(request):
    """Pantalla de setup amigable para registrar TOTP + backup codes."""
    try:
        from django_otp.plugins.otp_totp.models import TOTPDevice
        from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
    except ImportError:  # pragma: no cover
        messages.error(
            request,
            "django-otp no está instalado. Pedile a soporte que lo agregue.",
        )
        return redirect("admin:index")

    user = request.user
    enforced = bool(getattr(settings, "ADMIN_2FA_ENFORCED", False))

    confirmed_totp = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    pending_totp = TOTPDevice.objects.filter(user=user, confirmed=False).order_by("-id").first()
    static_dev = StaticDevice.objects.filter(user=user, confirmed=True).first()

    action = request.POST.get("action")

    if request.method == "POST" and action == "create_pending":
        # Borra cualquier dispositivo no confirmado previo y crea uno nuevo.
        TOTPDevice.objects.filter(user=user, confirmed=False).delete()
        TOTPDevice.objects.create(user=user, name="Dispositivo principal", confirmed=False)
        return redirect(reverse("admin_2fa_setup"))

    if request.method == "POST" and action == "verify":
        token = (request.POST.get("token") or "").strip()
        if not pending_totp:
            messages.error(request, "No hay dispositivo pendiente. Generá uno primero.")
            return redirect(reverse("admin_2fa_setup"))
        if not token.isdigit() or len(token) not in (6, 7, 8):
            messages.error(request, "El código debe ser numérico (6 dígitos).")
            return redirect(reverse("admin_2fa_setup"))
        if pending_totp.verify_token(token):
            pending_totp.confirmed = True
            pending_totp.save(update_fields=["confirmed"])
            # Generamos 8 backup codes (StaticTokens) si no había.
            if not static_dev:
                static_dev = StaticDevice.objects.create(
                    user=user, name="Códigos de respaldo", confirmed=True,
                )
            else:
                static_dev.token_set.all().delete()
            backup_codes = []
            import secrets as _secrets
            for _ in range(8):
                code = _secrets.token_hex(4)  # 8 hex chars
                StaticToken.objects.create(device=static_dev, token=code)
                backup_codes.append(code)
            request.session["jheliz_2fa_backup_codes"] = backup_codes
            messages.success(
                request,
                "2FA activado correctamente. Guardá tus códigos de respaldo abajo.",
            )
            return redirect(reverse("admin_2fa_setup"))
        else:
            messages.error(request, "El código no coincide. Probá de nuevo.")
            return redirect(reverse("admin_2fa_setup"))

    if request.method == "POST" and action == "regen_backup":
        if not confirmed_totp:
            messages.error(request, "Primero activá tu TOTP.")
            return redirect(reverse("admin_2fa_setup"))
        if not static_dev:
            static_dev = StaticDevice.objects.create(
                user=user, name="Códigos de respaldo", confirmed=True,
            )
        else:
            static_dev.token_set.all().delete()
        backup_codes = []
        import secrets as _secrets
        for _ in range(8):
            code = _secrets.token_hex(4)
            StaticToken.objects.create(device=static_dev, token=code)
            backup_codes.append(code)
        request.session["jheliz_2fa_backup_codes"] = backup_codes
        messages.success(request, "Códigos regenerados. Los anteriores ya no sirven.")
        return redirect(reverse("admin_2fa_setup"))

    if request.method == "POST" and action == "remove":
        TOTPDevice.objects.filter(user=user).delete()
        StaticDevice.objects.filter(user=user).delete()
        request.session.pop("jheliz_2fa_backup_codes", None)
        messages.success(request, "2FA desactivado para tu cuenta.")
        return redirect(reverse("admin_2fa_setup"))

    # GET: armamos el contexto.
    qr_provisioning_uri = None
    secret_b32 = None
    if pending_totp:
        # config_url devuelve otpauth://totp/?secret=...&issuer=...
        qr_provisioning_uri = pending_totp.config_url
        # El "secret" base32 está en la config_url; lo extraemos para
        # mostrar también en texto por si la cámara no lee el QR.
        try:
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(qr_provisioning_uri).query)
            secret_b32 = (qs.get("secret") or [None])[0]
        except Exception:  # pragma: no cover
            secret_b32 = None

    backup_codes = request.session.pop("jheliz_2fa_backup_codes", None)

    ctx = _admin_context(
        request,
        title="Seguridad — 2FA",
        enforced=enforced,
        confirmed_totp=confirmed_totp,
        pending_totp=pending_totp,
        static_dev=static_dev,
        qr_provisioning_uri=qr_provisioning_uri,
        secret_b32=secret_b32,
        backup_codes=backup_codes,
    )
    return render(request, "admin/security_2fa.html", ctx)


# ---------------------------------------------------------------------------
# Bulk delivery — entregar en masa pedidos en preparación con stock disponible
# ---------------------------------------------------------------------------

def _bulk_deliver_order(order, actor=None):
    """Auto-asigna stock disponible a todos los items del pedido y entrega.

    Devuelve ``(delivered, missing_items)`` donde ``missing_items`` es la lista
    de items que no tuvieron stock disponible y por ende el pedido NO se
    entregó (queda en PREPARING sin tocar).
    """
    from catalog.models import StockItem
    from orders import emails
    from orders.models import Order, OrderItem

    items: list[OrderItem] = list(
        order.items.select_related("product", "plan", "stock_item").all()
    )
    if not items:
        return False, []

    missing: list[OrderItem] = []
    plan: list[tuple[OrderItem, StockItem | None]] = []

    with transaction.atomic():
        order_locked = (
            Order.objects.select_for_update().filter(pk=order.pk).first()
        )
        if order_locked is None or order_locked.status != Order.Status.PREPARING:
            # Alguien más ya movió el pedido; no lo tocamos.
            return False, []

        for item in items:
            existing = item.stock_item
            if existing is not None and existing.status == StockItem.Status.SOLD:
                plan.append((item, None))
                continue
            if existing is not None and existing.status in {
                StockItem.Status.AVAILABLE, StockItem.Status.RESERVED,
            }:
                stock = (
                    StockItem.objects.select_for_update()
                    .filter(
                        pk=existing.pk,
                        status__in=[StockItem.Status.AVAILABLE, StockItem.Status.RESERVED],
                    ).first()
                )
                if stock:
                    plan.append((item, stock))
                    continue

            plan_id = item.plan_id
            stock = (
                StockItem.objects.select_for_update()
                .filter(status=StockItem.Status.AVAILABLE, plan_id=plan_id)
                .order_by("id")
                .first()
            )
            if stock is None:
                missing.append(item)
                continue
            plan.append((item, stock))

        if missing:
            return False, missing

        for item, stock in plan:
            if stock is None:
                continue
            stock.status = StockItem.Status.SOLD
            stock.sold_at = timezone.now()
            stock.save(update_fields=["status", "sold_at"])
            item.stock_item = stock
            item.delivered_credentials = item.delivered_credentials or stock.credentials
            item.save(update_fields=["stock_item", "delivered_credentials"])

        order_locked.status = Order.Status.DELIVERED
        order_locked.delivered_at = timezone.now()
        order_locked.paid_at = order_locked.paid_at or order_locked.delivered_at
        order_locked.save(update_fields=["status", "delivered_at", "paid_at"])

    transaction.on_commit(lambda: _send_delivered_email(order_locked.pk))
    return True, []


def _send_delivered_email(order_id: int):
    from orders import emails
    from orders.models import Order

    order = Order.objects.filter(pk=order_id).first()
    if order is not None:
        emails.send_order_delivered(order)


@staff_member_required
def bulk_delivery_view(request):
    """Lista todos los pedidos PREPARING sin entregar con info de stock disponible."""
    from django.db.models import Count
    from catalog.models import StockItem
    from orders.models import Order

    orders = list(
        Order.objects.filter(status=Order.Status.PREPARING)
        .select_related("user")
        .prefetch_related("items__product", "items__plan", "items__stock_item")
        .order_by("-paid_at", "-created_at")[:150]
    )

    plan_ids = set()
    for order in orders:
        for item in order.items.all():
            if item.plan_id:
                plan_ids.add(item.plan_id)

    avail_by_plan: dict[int, int] = {}
    if plan_ids:
        rows = (
            StockItem.objects.filter(status=StockItem.Status.AVAILABLE, plan_id__in=plan_ids)
            .values("plan_id")
            .annotate(avail=Count("id"))
        )
        avail_by_plan = {r["plan_id"]: r["avail"] for r in rows}

    rows = []
    total_deliverable = 0
    for order in orders:
        items_info = []
        order_deliverable = True
        for item in order.items.all():
            has_cred = bool(
                item.stock_item_id and item.stock_item and item.stock_item.status == "sold"
            ) or bool(item.delivered_credentials)
            avail = avail_by_plan.get(item.plan_id, 0) if item.plan_id else 0
            items_info.append({
                "item": item,
                "avail": avail,
                "has_cred": has_cred,
            })
            if not has_cred and avail <= 0:
                order_deliverable = False
        if order_deliverable:
            total_deliverable += 1
        rows.append({
            "order": order,
            "items": items_info,
            "deliverable": order_deliverable,
        })

    ctx = _admin_context(
        request,
        title="Entrega en masa",
        rows=rows,
        deliverable_count=total_deliverable,
        total_count=len(rows),
    )
    return render(request, "admin/bulk_delivery.html", ctx)


@staff_member_required
@require_POST
def bulk_deliver_one(request, order_id: int):
    from orders.models import Order

    order = get_object_or_404(Order, pk=order_id, status=Order.Status.PREPARING)
    delivered, missing = _bulk_deliver_order(order, actor=request.user)
    if delivered:
        messages.success(request, f"Pedido #{order.short_uuid} entregado.")
    else:
        if missing:
            names = ", ".join(f"{it.product_name} ({it.plan_name})" for it in missing)
            messages.warning(
                request,
                f"Pedido #{order.short_uuid} no se pudo entregar: falta stock para {names}.",
            )
        else:
            messages.info(
                request,
                f"Pedido #{order.short_uuid} ya no estaba en preparación.",
            )
    return redirect("admin_bulk_delivery")


@staff_member_required
@require_POST
def bulk_deliver_all(request):
    from orders.models import Order

    orders = list(
        Order.objects.filter(status=Order.Status.PREPARING)
        .order_by("paid_at", "created_at")[:100]
    )
    delivered = 0
    skipped = 0
    for order in orders:
        ok, _missing = _bulk_deliver_order(order, actor=request.user)
        if ok:
            delivered += 1
        else:
            skipped += 1
    messages.success(
        request,
        f"{delivered} pedido(s) entregado(s) · {skipped} omitido(s) por falta de stock.",
    )
    return redirect("admin_bulk_delivery")


# ---------------------------------------------------------------------------
# Audit log viewer
#
# `auditlog` registra cada create/update/delete de los modelos rastreados
# (Order, OrderItem, PaymentSettings, StockItem, Product, Plan), incluyendo
# actor, IP, timestamp y diff de campos. Esta vista expone esa información
# en una página filtrable para revisar quién cambió qué y cuándo, sin tener
# que entrar al admin de auditlog (que es muy crudo).
# ---------------------------------------------------------------------------

_AUDIT_ACTION_LABELS = {
    0: ("Creó", "create", "add_circle", "green"),
    1: ("Editó", "update", "edit", "blue"),
    2: ("Eliminó", "delete", "delete", "red"),
    3: ("Accedió", "access", "visibility", "yellow"),
}

_AUDIT_TONE_CLASSES = {
    "green": "border-green-500 bg-green-500/20 text-green-100",
    "blue": "border-blue-500 bg-blue-500/20 text-blue-100",
    "red": "border-red-500 bg-red-500/20 text-red-100",
    "yellow": "border-yellow-500 bg-yellow-500/20 text-yellow-100",
    "gray": "border-gray-500 bg-gray-500/20 text-gray-200",
}


def _parse_audit_changes(entry) -> list[dict]:
    """Convierte el JSON `changes` de auditlog en una lista de diffs legibles.

    Cada item: {field, old, new}. Trunca valores muy largos para no romper
    el layout de la tabla.
    """
    raw = getattr(entry, "changes", None)
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return []
    if not isinstance(raw, dict):
        return []
    diffs = []
    for field, change in raw.items():
        if isinstance(change, list) and len(change) == 2:
            old, new = change
        elif isinstance(change, dict):
            old = change.get("old")
            new = change.get("new")
        else:
            old = None
            new = change
        diffs.append({
            "field": field,
            "old": _truncate_for_display(old),
            "new": _truncate_for_display(new),
        })
    return diffs


def _truncate_for_display(value, limit: int = 200) -> str:
    s = "" if value is None else str(value)
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s


@staff_member_required
def auditlog_view(request):
    """Listado paginado del audit log con filtros.

    Filtros vía querystring:
      - ``model``: ``app_label.model`` (ej. ``orders.order``).
      - ``action``: ``create`` / ``update`` / ``delete`` / ``access``.
      - ``actor``: id numérico del usuario que hizo el cambio.
      - ``q``: búsqueda en ``object_repr`` o ``object_pk`` (LIKE).
      - ``days``: ventana de los últimos N días (default 30).
    """
    from auditlog.models import LogEntry
    from django.contrib.contenttypes.models import ContentType
    from accounts.models import User

    try:
        days = max(1, min(int(request.GET.get("days", "30")), 365))
    except (TypeError, ValueError):
        days = 30
    cutoff = timezone.now() - timedelta(days=days)

    qs = (
        LogEntry.objects.filter(timestamp__gte=cutoff)
        .select_related("content_type", "actor")
        .order_by("-timestamp")
    )

    model_filter = (request.GET.get("model") or "").strip().lower()
    if model_filter and "." in model_filter:
        app_label, model = model_filter.split(".", 1)
        ct = ContentType.objects.filter(app_label=app_label, model=model).first()
        if ct:
            qs = qs.filter(content_type=ct)

    action_filter = (request.GET.get("action") or "").strip().lower()
    action_value_map = {
        "create": LogEntry.Action.CREATE,
        "update": LogEntry.Action.UPDATE,
        "delete": LogEntry.Action.DELETE,
        "access": getattr(LogEntry.Action, "ACCESS", 3),
    }
    if action_filter in action_value_map:
        qs = qs.filter(action=action_value_map[action_filter])

    actor_filter = (request.GET.get("actor") or "").strip()
    if actor_filter.isdigit():
        qs = qs.filter(actor_id=int(actor_filter))

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(object_repr__icontains=q) | Q(object_pk__icontains=q)
        )

    # Paginación simple (no usamos django Paginator para no traer dependencias
    # nuevas de template; basta con limit + offset por página).
    try:
        page = max(1, int(request.GET.get("page", "1")))
    except (TypeError, ValueError):
        page = 1
    per_page = 50
    total = qs.count()
    entries = list(qs[(page - 1) * per_page : page * per_page])

    # Decorar cada entrada con el label del action, tono e icono, además del
    # diff parseado para mostrar inline (las primeras 3 líneas).
    rows = []
    for entry in entries:
        action_id = entry.action
        label, slug, icon, tone = _AUDIT_ACTION_LABELS.get(
            action_id, ("?", "other", "help", "gray")
        )
        diffs = _parse_audit_changes(entry)
        rows.append({
            "entry": entry,
            "action_label": label,
            "action_slug": slug,
            "action_icon": icon,
            "action_classes": _AUDIT_TONE_CLASSES[tone],
            "model_label": (
                f"{entry.content_type.app_label}.{entry.content_type.model}"
                if entry.content_type_id else "?"
            ),
            "diffs": diffs,
            "diff_preview": diffs[:3],
            "diff_more": max(0, len(diffs) - 3),
        })

    # Opciones para los selects de filtro: solo modelos efectivamente
    # registrados en auditlog (los que aparecen en LogEntry).
    model_options_qs = (
        LogEntry.objects.filter(timestamp__gte=cutoff)
        .values("content_type__app_label", "content_type__model")
        .distinct()
        .order_by("content_type__app_label", "content_type__model")
    )
    model_options = [
        {
            "value": f"{r['content_type__app_label']}.{r['content_type__model']}",
            "label": f"{r['content_type__app_label']}.{r['content_type__model']}",
        }
        for r in model_options_qs
        if r["content_type__app_label"] and r["content_type__model"]
    ]

    actor_options = list(
        User.objects.filter(is_staff=True)
        .order_by("username")
        .values("id", "username", "email")[:50]
    )

    has_prev = page > 1
    has_next = page * per_page < total

    ctx = _admin_context(
        request,
        title="Auditoría",
        rows=rows,
        total=total,
        page=page,
        per_page=per_page,
        has_prev=has_prev,
        has_next=has_next,
        model_filter=model_filter,
        action_filter=action_filter,
        actor_filter=actor_filter,
        q=q,
        days=days,
        model_options=model_options,
        actor_options=actor_options,
    )
    return render(request, "admin/auditlog.html", ctx)


@staff_member_required
def auditlog_detail(request, pk: int):
    """Vista de detalle de una entrada: diff completo del objeto cambiado."""
    from auditlog.models import LogEntry

    entry = get_object_or_404(
        LogEntry.objects.select_related("content_type", "actor"),
        pk=pk,
    )
    action_id = entry.action
    label, slug, icon, tone = _AUDIT_ACTION_LABELS.get(
        action_id, ("?", "other", "help", "gray")
    )
    diffs = _parse_audit_changes(entry)

    ctx = _admin_context(
        request,
        title=f"Auditoría #{entry.pk}",
        entry=entry,
        action_label=label,
        action_slug=slug,
        action_icon=icon,
        action_classes=_AUDIT_TONE_CLASSES[tone],
        model_label=(
            f"{entry.content_type.app_label}.{entry.content_type.model}"
            if entry.content_type_id else "?"
        ),
        diffs=diffs,
    )
    return render(request, "admin/auditlog_detail.html", ctx)


# ---------------------------------------------------------------------------
# Notificaciones Web Push (PWA): broadcast desde el admin
# ---------------------------------------------------------------------------

@staff_member_required
def push_broadcast_view(request):
    """Form para mandar una notificación push a todos los suscritos.

    Si VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY no están seteados en settings,
    muestra un cartel guía explicando cómo generarlos.
    """
    from accounts.models import PushSubscription
    from accounts import push as push_module

    subs_qs = PushSubscription.objects.filter(is_enabled=True)
    n_subs = subs_qs.count()
    n_subs_total = PushSubscription.objects.count()
    vapid_ok = push_module._vapid_configured()

    if request.method == "POST" and vapid_ok:
        title = (request.POST.get("title") or "").strip()
        body = (request.POST.get("body") or "").strip()
        url = (request.POST.get("url") or "/").strip()
        icon = (request.POST.get("icon") or "").strip()
        only_users = request.POST.get("only_users") == "on"
        if not title or not body:
            messages.error(request, "Título y mensaje son obligatorios.")
        else:
            target_qs = subs_qs.select_related("user")
            if only_users:
                target_qs = target_qs.filter(user__isnull=False)
            sent, failed = push_module.broadcast(
                target_qs, title=title, body=body, url=url, icon=icon,
            )
            if failed == 0:
                messages.success(
                    request,
                    f"Notificación enviada a {sent} suscriptor{'es' if sent != 1 else ''}.",
                )
            else:
                messages.warning(
                    request,
                    f"Notificación: {sent} ok, {failed} fallidas (las fallidas se desactivan al 3er intento).",
                )
            return redirect("admin_push_broadcast")

    ctx = _admin_context(
        request,
        title="Notificaciones push",
        n_subs=n_subs,
        n_subs_total=n_subs_total,
        vapid_ok=vapid_ok,
        recent_subs=list(subs_qs.select_related("user").order_by("-created_at")[:20]),
    )
    return render(request, "admin/push_broadcast.html", ctx)


# ---------------------------------------------------------------------------
# Dashboard avanzado (analítica profunda)
# ---------------------------------------------------------------------------

@staff_member_required
def advanced_dashboard_view(request):
    """Analítica profunda del negocio: heatmap horario, cohortes de retención,
    funnel de conversión, performance de distribuidores, tasa de renovación.

    Complementa /reports/ y /reports/charts/ que ya muestran totales y top
    productos. Acá se enfocan métricas que requieren cómputo y dan insights
    accionables (ej. en qué hora/día tener soporte activo, cuántos clientes
    repiten compra).
    """
    from accounts.models import Role
    from orders.models import Order, OrderItem

    paid_statuses = (
        Order.Status.PAID, Order.Status.PREPARING, Order.Status.DELIVERED,
    )
    paid_qs = Order.objects.filter(status__in=paid_statuses)
    now = timezone.localtime()
    today = now.date()

    # =====================================================================
    # 1. HEATMAP horario (24 hrs × 7 días) — últimos 90 días
    # =====================================================================
    start_90 = timezone.now() - timedelta(days=90)
    # Estructura: heatmap[day_of_week][hour] = count
    heatmap = [[0 for _ in range(24)] for _ in range(7)]
    for paid_at in paid_qs.filter(paid_at__gte=start_90).values_list("paid_at", flat=True):
        if not paid_at:
            continue
        local = timezone.localtime(paid_at)
        # weekday(): 0 = lunes, 6 = domingo
        dow = local.weekday()
        hour = local.hour
        heatmap[dow][hour] += 1
    # Para el chart: max value (para escalar la opacidad)
    heatmap_max = max((max(row) for row in heatmap), default=0)
    # Top 3 (dow, hour) con más ventas
    top_slots = []
    for dow in range(7):
        for hour in range(24):
            if heatmap[dow][hour] > 0:
                top_slots.append((heatmap[dow][hour], dow, hour))
    top_slots.sort(reverse=True)
    top_slots = top_slots[:3]
    dow_names = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    top_slots_labels = [
        f"{dow_names[dow]} {hour:02d}:00 — {count} ventas"
        for count, dow, hour in top_slots
    ]

    # =====================================================================
    # 2. COHORTES DE RETENCIÓN (último 6 meses)
    # =====================================================================
    # Para cada mes M (cohort), de los emails que compraron en M, ¿qué % volvió
    # a comprar en M+1, M+2, ..., M+5?
    cohorts = []
    cursor = today.replace(day=1)
    cohort_months = []
    for _ in range(6):
        cohort_months.append(cursor)
        if cursor.month == 1:
            cursor = cursor.replace(year=cursor.year - 1, month=12)
        else:
            cursor = cursor.replace(month=cursor.month - 1)
    cohort_months.reverse()  # del más antiguo al más reciente

    # Para cada cohort, identificamos los emails que compraron por primera vez
    # en ese mes, y vemos cuántos volvieron en los meses siguientes.
    six_months_ago = timezone.make_aware(
        datetime.combine(cohort_months[0], datetime.min.time())
    )
    # Mapa email -> primer mes (year, month)
    first_purchase = {}
    # Mapa email -> set de meses con compras
    purchase_months = {}
    for email, paid_at in paid_qs.filter(paid_at__gte=six_months_ago, email__gt="").values_list("email", "paid_at"):
        if not paid_at or not email:
            continue
        local = timezone.localtime(paid_at)
        month_key = (local.year, local.month)
        purchase_months.setdefault(email, set()).add(month_key)
        # Buscamos el primer mes para este email globalmente.
        if email not in first_purchase or month_key < first_purchase[email]:
            first_purchase[email] = month_key

    for idx, m in enumerate(cohort_months):
        cohort_key = (m.year, m.month)
        cohort_emails = [e for e, fp in first_purchase.items() if fp == cohort_key]
        n_cohort = len(cohort_emails)
        retention_row = []
        for offset in range(6):
            # Mes M + offset
            target_month = m
            for _ in range(offset):
                if target_month.month == 12:
                    target_month = target_month.replace(year=target_month.year + 1, month=1)
                else:
                    target_month = target_month.replace(month=target_month.month + 1)
            target_key = (target_month.year, target_month.month)
            if offset == 0:
                # 100% del cohort por definición.
                retention_row.append(100 if n_cohort > 0 else 0)
            else:
                # Solo computamos si el target_month ya pasó.
                target_first_day = target_month
                if target_first_day > today:
                    retention_row.append(None)
                else:
                    returners = sum(
                        1 for e in cohort_emails
                        if target_key in purchase_months.get(e, set())
                    )
                    pct = round((returners / n_cohort) * 100) if n_cohort > 0 else 0
                    retention_row.append(pct)
        cohorts.append({
            "label": m.strftime("%b %y"),
            "size": n_cohort,
            "row": retention_row,
        })

    # =====================================================================
    # 3. FUNNEL DE CONVERSIÓN (últimos 30 días)
    # =====================================================================
    last_30 = timezone.now() - timedelta(days=30)
    funnel_qs = Order.objects.filter(created_at__gte=last_30)
    funnel_counts = {
        "creados": funnel_qs.count(),
        "verificando": funnel_qs.filter(status=Order.Status.VERIFYING).count(),
        "pagados": funnel_qs.filter(
            status__in=(Order.Status.PAID, Order.Status.PREPARING, Order.Status.DELIVERED),
        ).count(),
        "entregados": funnel_qs.filter(status=Order.Status.DELIVERED).count(),
        "cancelados": funnel_qs.filter(
            status__in=(Order.Status.CANCELED, Order.Status.FAILED),
        ).count(),
    }
    # Tasa de conversión total (creados → entregados).
    if funnel_counts["creados"] > 0:
        conversion_rate = round(
            funnel_counts["entregados"] / funnel_counts["creados"] * 100, 1
        )
        # Tasa de pago (creados → pagados) – descarta pendientes.
        payment_rate = round(
            funnel_counts["pagados"] / funnel_counts["creados"] * 100, 1
        )
    else:
        conversion_rate = 0.0
        payment_rate = 0.0

    # =====================================================================
    # 4. PERFORMANCE DE DISTRIBUIDORES (últimos 30 días)
    # =====================================================================
    from accounts.models import User
    distri_perf = list(
        User.objects.filter(role=Role.DISTRIBUIDOR, distributor_approved=True)
        .annotate(
            orders_30d=Count(
                "orders", filter=Q(
                    orders__status__in=paid_statuses,
                    orders__paid_at__gte=last_30,
                ),
                distinct=True,
            ),
            revenue_30d=Sum(
                "orders__total", filter=Q(
                    orders__status__in=paid_statuses,
                    orders__paid_at__gte=last_30,
                ),
            ),
        )
        .order_by("-revenue_30d")[:10]
    )
    distri_total_30d = sum(
        (d.revenue_30d or Decimal("0") for d in distri_perf), Decimal("0")
    )

    # =====================================================================
    # 5. TASA DE RENOVACIÓN (heurística: clientes con 2+ pedidos del mismo prod)
    # =====================================================================
    # Tomamos OrderItems de los últimos 6 meses agrupados por (email, product).
    # Si hay 2+ entradas, el cliente "renovó" ese producto.
    repeat_rows = (
        OrderItem.objects
        .filter(
            order__status__in=paid_statuses,
            order__paid_at__gte=six_months_ago,
            order__email__gt="",
        )
        .values("order__email", "product_name")
        .annotate(c=Count("id"))
        .filter(c__gte=2)
    )
    n_repeat_pairs = repeat_rows.count()
    n_unique_pairs = (
        OrderItem.objects
        .filter(
            order__status__in=paid_statuses,
            order__paid_at__gte=six_months_ago,
            order__email__gt="",
        )
        .values("order__email", "product_name")
        .distinct()
        .count()
    )
    if n_unique_pairs > 0:
        renewal_rate = round((n_repeat_pairs / n_unique_pairs) * 100, 1)
    else:
        renewal_rate = 0.0

    # =====================================================================
    # 6. COMPARATIVAS (esta semana vs anterior, este mes vs anterior)
    # =====================================================================
    today_dt = timezone.localtime()

    def _revenue_in(start_dt, end_dt):
        agg = paid_qs.filter(
            paid_at__gte=start_dt, paid_at__lt=end_dt,
        ).aggregate(rev=Sum("total"), n=Count("id"))
        return float(agg["rev"] or 0), agg["n"] or 0

    week_start = today_dt - timedelta(days=today_dt.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    last_week_start = week_start - timedelta(days=7)
    this_week_rev, this_week_n = _revenue_in(week_start, today_dt + timedelta(days=1))
    last_week_rev, last_week_n = _revenue_in(last_week_start, week_start)

    def _pct(curr, prev):
        if prev > 0:
            return round((curr - prev) / prev * 100, 1)
        if curr > 0:
            return 100.0
        return 0.0

    week_trend = _pct(this_week_rev, last_week_rev)

    month_start = today_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 1:
        last_month_start = month_start.replace(year=month_start.year - 1, month=12)
    else:
        last_month_start = month_start.replace(month=month_start.month - 1)
    this_month_rev, this_month_n = _revenue_in(month_start, today_dt + timedelta(days=1))
    last_month_rev, last_month_n = _revenue_in(last_month_start, month_start)
    month_trend = _pct(this_month_rev, last_month_rev)

    ctx = _admin_context(
        request,
        title="Dashboard avanzado",
        currency_symbol=settings.DEFAULT_CURRENCY_SYMBOL,
        # Heatmap
        heatmap=heatmap,
        heatmap_max=heatmap_max,
        heatmap_json=json.dumps(heatmap),
        top_slots_labels=top_slots_labels,
        # Cohortes
        cohorts=cohorts,
        # Funnel
        funnel_counts=funnel_counts,
        conversion_rate=conversion_rate,
        payment_rate=payment_rate,
        # Distri
        distri_perf=distri_perf,
        distri_total_30d=distri_total_30d,
        # Renovaciones
        renewal_rate=renewal_rate,
        n_repeat_pairs=n_repeat_pairs,
        n_unique_pairs=n_unique_pairs,
        # Comparativas
        this_week_rev=this_week_rev, last_week_rev=last_week_rev,
        this_week_n=this_week_n, last_week_n=last_week_n,
        week_trend=week_trend,
        this_month_rev=this_month_rev, last_month_rev=last_month_rev,
        this_month_n=this_month_n, last_month_n=last_month_n,
        month_trend=month_trend,
    )
    return render(request, "admin/advanced_dashboard.html", ctx)


# ---------------------------------------------------------------------------
# Crear pedido rápido (registro express de venta ya pagada)
# ---------------------------------------------------------------------------

@staff_member_required
def quick_order_create(request):
    """Vista express para registrar una venta ya cerrada.

    El admin viene acá cuando un cliente ya pagó por fuera (Yape directo,
    efectivo, transferencia) y necesita registrar la venta + entregar el
    stock en un solo paso. Reduce el flujo de "crear pedido > agregar item
    > marcar pagado > entregar credenciales" a un único formulario.
    """
    from django.contrib.auth import get_user_model
    from catalog.models import Plan, Product, StockItem
    from orders.models import Order, OrderItem
    from orders import emails as order_emails
    from orders import telegram as order_telegram

    User = get_user_model()

    plans_qs = (
        Plan.objects.filter(is_active=True, product__is_active=True)
        .select_related("product")
        .order_by("product__name", "duration_days")
    )

    if request.method == "POST":
        # ---- Lectura del POST -------------------------------------------
        email = (request.POST.get("email") or "").strip().lower()
        full_name = (request.POST.get("full_name") or "").strip()
        phone = (request.POST.get("phone") or "").strip()
        plan_id = request.POST.get("plan_id") or ""
        quantity_raw = request.POST.get("quantity") or "1"
        payment_method = (request.POST.get("payment_method") or "manual").strip()
        paid_at_raw = (request.POST.get("paid_at") or "").strip()
        notes = (request.POST.get("notes") or "").strip()
        auto_deliver = request.POST.get("auto_deliver") == "on"
        manual_credentials = (request.POST.get("manual_credentials") or "").strip()
        send_email = request.POST.get("send_email") == "on"

        errors = []
        if not email or "@" not in email:
            errors.append("Email del cliente inválido o vacío.")
        if not plan_id:
            errors.append("Tenés que elegir un plan.")
        try:
            quantity = max(1, min(20, int(quantity_raw)))
        except (TypeError, ValueError):
            errors.append("Cantidad inválida.")
            quantity = 1

        plan = None
        if plan_id:
            plan = plans_qs.filter(pk=plan_id).first()
            if plan is None:
                errors.append("El plan elegido no existe o está inactivo.")

        # paid_at: si el admin no la setea, usamos ahora.
        paid_at = timezone.now()
        if paid_at_raw:
            try:
                paid_at_naive = datetime.fromisoformat(paid_at_raw)
                if timezone.is_naive(paid_at_naive):
                    paid_at = timezone.make_aware(paid_at_naive)
                else:
                    paid_at = paid_at_naive
            except ValueError:
                errors.append("Fecha de pago inválida (usa AAAA-MM-DDTHH:MM).")

        if errors:
            for err in errors:
                messages.error(request, err)
            return _quick_order_render(
                request, plans_qs,
                preset={
                    "email": email,
                    "full_name": full_name,
                    "phone": phone,
                    "plan_id": plan_id,
                    "quantity": quantity_raw,
                    "payment_method": payment_method,
                    "paid_at": paid_at_raw,
                    "notes": notes,
                    "auto_deliver": auto_deliver,
                    "manual_credentials": manual_credentials,
                    "send_email": send_email,
                },
            )

        # ---- Get or create cliente --------------------------------------
        with transaction.atomic():
            user = User.objects.filter(email__iexact=email).first()
            created_user = False
            if user is None:
                # Username único: usamos el email truncado (Django permite
                # username con `@`).
                base_username = email[:150]
                username = base_username
                suffix = 1
                while User.objects.filter(username=username).exists():
                    suffix += 1
                    username = f"{base_username[:140]}-{suffix}"
                first_name = full_name.split(" ", 1)[0] if full_name else ""
                last_name = full_name.split(" ", 1)[1] if " " in full_name else ""
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    phone=phone,
                )
                # Password aleatorio (cliente lo resetea con "olvidé mi clave").
                user.set_unusable_password()
                user.save(update_fields=["password"])
                created_user = True
            else:
                # Actualizamos teléfono si vino y el user no tenía.
                if phone and not user.phone:
                    user.phone = phone
                    user.save(update_fields=["phone"])

            # ---- Crear order ------------------------------------------------
            unit_price = plan.price_for(user)
            order = Order.objects.create(
                user=user,
                email=email,
                phone=phone or user.phone,
                channel=Order.Channel.MANUAL,
                status=Order.Status.PAID,
                payment_provider=payment_method,
                paid_at=paid_at,
                notes=notes,
            )
            item = OrderItem.objects.create(
                order=order,
                product=plan.product,
                plan=plan,
                product_name=plan.product.name,
                plan_name=plan.name,
                unit_price=unit_price,
                quantity=quantity,
            )
            order.recompute_total()

            # ---- Auto-entrega opcional --------------------------------------
            delivered = False
            if auto_deliver:
                # El signal post_save de OrderItem ya pudo haber reservado
                # un StockItem (status=RESERVED) automáticamente. Lo usamos
                # si está disponible; si no, buscamos uno AVAILABLE.
                item.refresh_from_db()
                stock = None
                if item.stock_item_id:
                    candidate = (
                        StockItem.objects.select_for_update()
                        .filter(
                            pk=item.stock_item_id,
                            status__in=[
                                StockItem.Status.AVAILABLE,
                                StockItem.Status.RESERVED,
                            ],
                        )
                        .first()
                    )
                    if candidate is not None:
                        stock = candidate
                if stock is None:
                    stock = (
                        StockItem.objects.select_for_update()
                        .filter(
                            product_id=plan.product_id,
                            status=StockItem.Status.AVAILABLE,
                        )
                        .filter(
                            Q(plan_id=plan.pk) | Q(plan__isnull=True)
                        )
                        .order_by("created_at")
                        .first()
                    )
                now = timezone.now()
                if stock is not None:
                    stock.status = StockItem.Status.SOLD
                    stock.sold_at = now
                    stock.save(update_fields=["status", "sold_at"])
                    item.stock_item = stock
                    item.delivered_credentials = stock.credentials
                    if plan.duration_days and not item.expires_at:
                        item.expires_at = now + timedelta(days=plan.duration_days)
                    item.save(update_fields=[
                        "stock_item", "delivered_credentials", "expires_at",
                    ])
                    delivered = True
                elif manual_credentials:
                    # Prioridad 2: credenciales escritas a mano.
                    item.delivered_credentials = manual_credentials
                    if plan.duration_days and not item.expires_at:
                        item.expires_at = now + timedelta(days=plan.duration_days)
                    item.save(update_fields=["delivered_credentials", "expires_at"])
                    delivered = True

                if delivered:
                    order.status = Order.Status.DELIVERED
                    order.delivered_at = now
                    order.save(update_fields=["status", "delivered_at"])

        # ---- Notificaciones (fuera de la transacción) ---------------------
        if delivered and send_email:
            try:
                order_emails.send_order_delivered(order)
            except Exception:
                # No bloqueamos: queda registrado en EmailLog si falla.
                pass

        try:
            label = "creado" if not delivered else "creado + entregado"
            order_telegram.notify_admin(
                f"📝 Pedido manual {label}: #{order.short_uuid} · "
                f"{plan.product.name} {plan.name} · S/ {order.total} · {email}"
                + (" (cliente nuevo)" if created_user else "")
            )
        except Exception:
            pass

        if delivered:
            messages.success(
                request,
                f"Pedido #{order.short_uuid} registrado y entregado. "
                + ("Email enviado al cliente." if send_email else "")
            )
        elif auto_deliver and not delivered:
            messages.warning(
                request,
                f"Pedido #{order.short_uuid} registrado, pero NO se entregó: "
                "no hay stock disponible para ese plan ni cargaste credenciales "
                "manuales. Entregalo desde el detalle del pedido."
            )
        else:
            messages.success(
                request,
                f"Pedido #{order.short_uuid} registrado como pagado. "
                "Entregalo cuando quieras desde el detalle."
            )

        # Después de crear, volvemos al detalle del pedido.
        return redirect(
            "admin:orders_order_change", object_id=order.pk
        )

    return _quick_order_render(request, plans_qs)


def _quick_order_render(request, plans_qs, preset=None):
    """Renderiza el formulario de pedido rápido."""
    preset = preset or {}
    # Agrupamos planes por producto para el select.
    plans_by_product: dict[str, list] = {}
    for plan in plans_qs:
        plans_by_product.setdefault(plan.product.name, []).append(plan)

    ctx = _admin_context(
        request,
        title="Crear pedido rápido",
        plans_by_product=plans_by_product,
        preset=preset,
        payment_methods=[
            ("manual", "Manual / efectivo"),
            ("yape", "Yape"),
            ("plin", "Plin"),
            ("transferencia", "Transferencia bancaria"),
            ("mercadopago", "Mercado Pago"),
        ],
        now_local=timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
    )
    return render(request, "admin/orders/quick_create.html", ctx)
