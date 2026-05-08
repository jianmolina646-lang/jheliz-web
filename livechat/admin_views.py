"""Vistas del lado admin del chat en vivo (en `/panel-jheliz-2026/livechat/`)."""

from __future__ import annotations

from datetime import datetime

from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import ChatMessage, ChatRoom


@staff_member_required
def chat_index(request: HttpRequest):
    """Lista de salas de chat (bandeja del operador)."""
    show_closed = request.GET.get("closed") == "1"
    qs = ChatRoom.objects.all()
    if not show_closed:
        qs = qs.filter(status=ChatRoom.Status.OPEN)
    qs = qs.annotate(message_count=Count("messages")).order_by(
        "-last_message_at", "-created_at",
    )

    rooms = list(qs[:200])
    # Pre-compute admin_unread y customer-side info para no pegarle a la BD
    # múltiples veces en el template.
    enriched: list[dict] = []
    for r in rooms:
        last = r.messages.order_by("-created_at").first()
        enriched.append({
            "room": r,
            "admin_unread": r.admin_unread_count,
            "last_message": last,
            "is_customer_typing": False,  # placeholder para futura mejora
        })

    open_count = ChatRoom.objects.filter(status=ChatRoom.Status.OPEN).count()
    total_unread = sum(item["admin_unread"] for item in enriched)

    return render(
        request,
        "admin/livechat/index.html",
        {
            "rooms_data": enriched,
            "show_closed": show_closed,
            "open_count": open_count,
            "total_unread": total_unread,
            "title": "Chats en vivo",
        },
    )


@staff_member_required
def chat_detail(request: HttpRequest, room_id: int):
    """Detalle de una sala — vista del operador."""
    room = get_object_or_404(ChatRoom, pk=room_id)
    room.mark_admin_seen()
    return render(
        request,
        "admin/livechat/detail.html",
        {
            "room": room,
            "messages_thread": list(room.messages.all()),
            "messages_poll_url": reverse(
                "admin_livechat_messages", args=[room.pk]
            ),
            "title": f"Chat con {room.display_name}",
        },
    )


@staff_member_required
@require_POST
def chat_reply(request: HttpRequest, room_id: int):
    room = get_object_or_404(ChatRoom, pk=room_id)
    body = (request.POST.get("body") or "").strip()
    if not body:
        if request.headers.get("HX-Request"):
            return chat_messages_partial(request, room_id)
        return redirect("admin_livechat_detail", room_id=room.pk)

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
        return chat_messages_partial(request, room_id)
    return redirect("admin_livechat_detail", room_id=room.pk)


@staff_member_required
@require_GET
def chat_messages_partial(request: HttpRequest, room_id: int):
    """HTMX poll endpoint — devuelve solo el partial con el thread."""
    room = get_object_or_404(ChatRoom, pk=room_id)
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
def chat_close(request: HttpRequest, room_id: int):
    room = get_object_or_404(ChatRoom, pk=room_id)
    room.status = ChatRoom.Status.CLOSED
    room.save(update_fields=["status"])
    return redirect("admin_livechat_index")


@staff_member_required
@require_POST
def chat_reopen(request: HttpRequest, room_id: int):
    room = get_object_or_404(ChatRoom, pk=room_id)
    room.status = ChatRoom.Status.OPEN
    room.save(update_fields=["status"])
    return redirect("admin_livechat_detail", room_id=room.pk)


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
