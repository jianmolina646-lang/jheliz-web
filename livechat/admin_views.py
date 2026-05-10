"""Vistas del lado admin del chat en vivo (en `/panel-jheliz-2026/livechat/`).

Diseño 2026: split-pane estilo Gmail/WhatsApp Web.
- La lista de salas vive a la izquierda y el panel de conversación a la derecha.
- Cuando el operador hace click en una sala, htmx carga el panel derecho con
  `chat_room_partial` sin recargar la página entera.
- La URL se actualiza vía `hx-push-url` para que refrescar / compartir vuelva
  a abrir la sala correcta.
"""

from __future__ import annotations

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.db.models import Count
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import ChatMessage, ChatRoom


def _build_rooms_payload(*, show_closed: bool, limit: int = 200) -> tuple[list[dict], int, int]:
    """Construye la lista enriquecida de salas para la columna izquierda."""
    qs = ChatRoom.objects.all()
    if not show_closed:
        qs = qs.filter(status=ChatRoom.Status.OPEN)
    qs = qs.annotate(message_count=Count("messages")).order_by(
        "-last_message_at", "-created_at",
    )

    rooms = list(qs[:limit])
    enriched: list[dict] = []
    for r in rooms:
        last = r.messages.order_by("-created_at").first()
        enriched.append({
            "room": r,
            "admin_unread": r.admin_unread_count,
            "last_message": last,
        })

    open_count = ChatRoom.objects.filter(status=ChatRoom.Status.OPEN).count()
    total_unread = sum(item["admin_unread"] for item in enriched)
    return enriched, open_count, total_unread


def _room_pane_context(request: HttpRequest, room: ChatRoom) -> dict:
    """Contexto compartido para renderizar el panel derecho (header + thread +
    reply form). Marca al admin como "visto" como side-effect."""
    room.mark_admin_seen()
    return {
        "room": room,
        "messages_thread": list(room.messages.all()),
        "messages_poll_url": reverse(
            "admin_livechat_messages", args=[room.pk]
        ),
        "reply_url": reverse("admin_livechat_reply", args=[room.pk]),
        "close_url": reverse("admin_livechat_close", args=[room.pk]),
        "reopen_url": reverse("admin_livechat_reopen", args=[room.pk]),
    }


@staff_member_required
def chat_index(request: HttpRequest):
    """Lista de salas (columna izquierda) + opcionalmente una sala abierta a
    la derecha cuando se navega con `?room=<id>`."""
    show_closed = request.GET.get("closed") == "1"
    enriched, open_count, total_unread = _build_rooms_payload(show_closed=show_closed)

    selected_room = None
    selected_ctx: dict = {}
    room_id_raw = request.GET.get("room") or ""
    if room_id_raw.isdigit():
        selected_room = ChatRoom.objects.filter(pk=int(room_id_raw)).first()
        if selected_room is not None:
            selected_ctx = _room_pane_context(request, selected_room)

    context = {
        **admin.site.each_context(request),
        "rooms_data": enriched,
        "show_closed": show_closed,
        "open_count": open_count,
        "total_unread": total_unread,
        "selected_room": selected_room,
        "title": "Chats en vivo",
    }
    context.update(selected_ctx)
    return render(request, "admin/livechat/index.html", context)


@staff_member_required
@require_GET
def chat_room_partial(request: HttpRequest, room_id: int):
    """Devuelve solo el panel derecho (cuando htmx lo solicita al clickear
    una sala en la lista). Marca admin_seen como side-effect."""
    room = get_object_or_404(ChatRoom, pk=room_id)
    ctx = _room_pane_context(request, room)
    return render(request, "admin/livechat/_room_pane.html", ctx)


@staff_member_required
def chat_detail(request: HttpRequest, room_id: int):
    """Detalle directo de una sala. Renderiza el split-pane con la sala
    seleccionada — útil para deep-links viejos / notificaciones / bookmarks
    de operadores. Sirve la misma plantilla que ``chat_index`` para no
    fragmentar la UX."""
    room = get_object_or_404(ChatRoom, pk=room_id)
    show_closed = request.GET.get("closed") == "1"
    enriched, open_count, total_unread = _build_rooms_payload(show_closed=show_closed)
    selected_ctx = _room_pane_context(request, room)
    context = {
        **admin.site.each_context(request),
        "rooms_data": enriched,
        "show_closed": show_closed,
        "open_count": open_count,
        "total_unread": total_unread,
        "selected_room": room,
        "title": f"Chat con {room.display_name}",
    }
    context.update(selected_ctx)
    return render(request, "admin/livechat/index.html", context)


def _render_messages_partial(request: HttpRequest, room: ChatRoom):
    """Render del thread completo para el polling de htmx y la respuesta
    tras un POST de reply."""
    room.mark_admin_seen()
    return render(
        request,
        "admin/livechat/_messages.html",
        {
            "room": room,
            "messages_thread": list(room.messages.all()),
            "messages_poll_url": reverse(
                "admin_livechat_messages", args=[room.pk]
            ),
        },
    )


@staff_member_required
@require_POST
def chat_reply(request: HttpRequest, room_id: int):
    room = get_object_or_404(ChatRoom, pk=room_id)
    body = (request.POST.get("body") or "").strip()
    if not body:
        if request.headers.get("HX-Request"):
            return _render_messages_partial(request, room)
        return redirect(reverse("admin_livechat_index") + f"?room={room.pk}")

    body = body[:4000]
    with transaction.atomic():
        ChatMessage.objects.create(
            room=room,
            sender=ChatMessage.Sender.ADMIN,
            sender_user=request.user,
            body=body,
        )
        room.touch()
        room.mark_admin_seen()

    if request.headers.get("HX-Request"):
        return _render_messages_partial(request, room)
    return redirect(reverse("admin_livechat_index") + f"?room={room.pk}")


@staff_member_required
@require_GET
def chat_messages_partial(request: HttpRequest, room_id: int):
    """HTMX poll endpoint — devuelve solo el partial con el thread."""
    room = get_object_or_404(ChatRoom, pk=room_id)
    return _render_messages_partial(request, room)


@staff_member_required
@require_POST
def chat_close(request: HttpRequest, room_id: int):
    room = get_object_or_404(ChatRoom, pk=room_id)
    room.status = ChatRoom.Status.CLOSED
    room.save(update_fields=["status"])
    if request.headers.get("HX-Request"):
        ctx = _room_pane_context(request, room)
        return render(request, "admin/livechat/_room_pane.html", ctx)
    return redirect(reverse("admin_livechat_index") + f"?room={room.pk}")


@staff_member_required
@require_POST
def chat_reopen(request: HttpRequest, room_id: int):
    room = get_object_or_404(ChatRoom, pk=room_id)
    room.status = ChatRoom.Status.OPEN
    room.save(update_fields=["status"])
    if request.headers.get("HX-Request"):
        ctx = _room_pane_context(request, room)
        return render(request, "admin/livechat/_room_pane.html", ctx)
    return redirect(reverse("admin_livechat_index") + f"?room={room.pk}")


@staff_member_required
@require_GET
def chat_unread_count(request: HttpRequest):
    """Endpoint JSON consumido por el bell para mostrar el badge."""
    open_rooms = ChatRoom.objects.filter(status=ChatRoom.Status.OPEN)
    total_unread = 0
    rooms_with_unread = 0
    for room in open_rooms.only("id", "last_admin_seen_at"):
        # admin_unread_count cuenta mensajes del cliente posteriores al último vistazo
        qs = ChatMessage.objects.filter(
            room_id=room.pk, sender=ChatMessage.Sender.CUSTOMER,
        )
        if room.last_admin_seen_at:
            qs = qs.filter(created_at__gt=room.last_admin_seen_at)
        n = qs.count()
        if n > 0:
            rooms_with_unread += 1
            total_unread += n
    return JsonResponse({
        "ok": True,
        "open_rooms": open_rooms.count(),
        "rooms_with_unread": rooms_with_unread,
        "total_unread": total_unread,
        "now": timezone.now().isoformat(),
    })
