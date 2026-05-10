"""Endpoints públicos del chat en vivo (lado del visitante).

Tres endpoints simples:

* ``POST /chat/start/`` — el visitante inicia (o retoma) una conversación.
  Si manda un ``token`` válido en el body, devolvemos esa misma sala. Si no,
  creamos una nueva. La respuesta trae ``token`` que el navegador guarda en
  ``localStorage``.

* ``POST /chat/<token>/send/`` — el visitante manda un mensaje a la sala.

* ``GET /chat/<token>/poll/`` — devuelve mensajes desde un timestamp y marca
  como leídos los del admin para esta sala.

Diseñado para HTMX/fetch del lado público. JSON-only.
"""

from __future__ import annotations

import re
from datetime import datetime

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import ChatMessage, ChatRoom
from .telegram_notify import notify_admin_new_customer_message


_MAX_BODY = 4000  # cualquier cosa más larga lo cortamos para evitar abusos

# Imágenes adjuntas
_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
_ALLOWED_IMAGE_CT = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def _validate_image(uploaded) -> str | None:
    """Devuelve un mensaje de error si la imagen no es válida; None si OK."""
    if uploaded is None:
        return None
    if uploaded.size > _MAX_IMAGE_BYTES:
        return "La imagen es demasiado grande (máximo 5 MB)."
    ct = (getattr(uploaded, "content_type", "") or "").lower()
    if ct and ct not in _ALLOWED_IMAGE_CT:
        return "Solo se permiten imágenes JPG, PNG, GIF o WebP."
    return None


def _client_ip(request: HttpRequest) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def _serialize_message(m: ChatMessage) -> dict:
    return {
        "id": m.pk,
        "sender": m.sender,
        "body": m.body,
        "image_url": m.image.url if m.image else None,
        "created_at": m.created_at.isoformat(),
    }


def _serialize_room(room: ChatRoom) -> dict:
    return {
        "token": room.token,
        "status": room.status,
        "customer_name": room.customer_name,
        "customer_email": room.customer_email,
        "created_at": room.created_at.isoformat(),
    }


@ensure_csrf_cookie
@require_POST
def start(request: HttpRequest):
    """Crea o retoma una sala de chat para el visitante.

    Body (form-urlencoded o JSON):
      token (opcional): si el navegador ya tiene una sala, se reutiliza.
      name (opcional): nombre del visitante.
      email (opcional): correo del visitante.
      page_url (opcional): URL desde donde abrió el chat.
    """
    token = (request.POST.get("token") or "").strip()
    name = (request.POST.get("name") or "").strip()[:80]
    email = (request.POST.get("email") or "").strip().lower()[:200]
    page_url = (request.POST.get("page_url") or "").strip()[:500]

    if email:
        try:
            validate_email(email)
        except ValidationError:
            return JsonResponse(
                {"ok": False, "error": "Ese correo no parece válido."},
                status=400,
            )

    room: ChatRoom | None = None
    if token:
        room = ChatRoom.objects.filter(token=token).first()

    if room is None:
        room = ChatRoom(
            page_url=page_url,
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:255],
            ip=_client_ip(request),
        )
        if request.user.is_authenticated:
            room.user = request.user
            room.customer_name = (
                request.user.get_full_name()
                or getattr(request.user, "username", "")
            )[:80]
            room.customer_email = (
                getattr(request.user, "email", "") or ""
            ).lower()[:200]
        room.customer_name = name or room.customer_name
        room.customer_email = email or room.customer_email
        room.save()

    # Update name/email si vienen y la sala no tiene aún (no pisamos lo del user).
    update_fields: list[str] = []
    if name and not room.customer_name:
        room.customer_name = name
        update_fields.append("customer_name")
    if email and not room.customer_email:
        room.customer_email = email
        update_fields.append("customer_email")
    if update_fields:
        room.save(update_fields=update_fields)

    # Marcamos al cliente como "viendo ahora" → al admin se le aclaran las no leídas
    # del lado del cliente.
    room.mark_customer_seen()

    return JsonResponse({
        "ok": True,
        "room": _serialize_room(room),
        "messages": [_serialize_message(m) for m in room.messages.all()[:200]],
    })


_TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-]{20,48}$")


def _get_room_or_404(token: str) -> ChatRoom:
    if not _TOKEN_RE.match(token or ""):
        from django.http import Http404
        raise Http404("Token inválido.")
    return get_object_or_404(ChatRoom, token=token)


@require_POST
def send(request: HttpRequest, token: str):
    room = _get_room_or_404(token)
    body = (request.POST.get("body") or "").strip()[:_MAX_BODY]
    image = request.FILES.get("image")

    err = _validate_image(image)
    if err:
        return JsonResponse({"ok": False, "error": err}, status=400)

    if not body and image is None:
        return JsonResponse(
            {"ok": False, "error": "Escribí un mensaje o adjuntá una imagen."},
            status=400,
        )

    with transaction.atomic():
        msg = ChatMessage.objects.create(
            room=room,
            sender=ChatMessage.Sender.CUSTOMER,
            body=body,
            image=image,
        )
        room.touch()

    notify_admin_new_customer_message(room, msg)

    return JsonResponse({
        "ok": True,
        "message": _serialize_message(msg),
    })


@require_GET
def poll(request: HttpRequest, token: str):
    """Devuelve mensajes desde ``since`` (ISO o id) y marca-vistos del lado cliente."""
    room = _get_room_or_404(token)
    since_id = request.GET.get("since_id")
    since_ts = request.GET.get("since")

    qs = room.messages.all()
    if since_id and since_id.isdigit():
        qs = qs.filter(pk__gt=int(since_id))
    elif since_ts:
        try:
            dt = datetime.fromisoformat(since_ts)
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_default_timezone())
            qs = qs.filter(created_at__gt=dt)
        except (ValueError, TypeError):
            pass

    messages = [_serialize_message(m) for m in qs]
    if messages:
        # Cliente está mirando → marcamos los del admin como vistos.
        room.mark_customer_seen()

    return JsonResponse({
        "ok": True,
        "room_status": room.status,
        "messages": messages,
        "now": timezone.now().isoformat(),
    })
