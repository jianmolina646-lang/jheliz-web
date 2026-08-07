"""Notificaciones del panel administrativo."""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone


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
    """Formatea un Decimal como '$49.90' (o el símbolo configurado)."""
    if amount is None:
        return ""
    symbol = (currency or settings.DEFAULT_CURRENCY_SYMBOL or "$").strip()
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
            "title": f"Comprobante por aprobar · #{order.display_number} · {_format_money(order.total, order.currency)}",
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
            "title": f"Pedido en preparación · #{order.display_number} · {_format_money(order.total, order.currency)}",
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
