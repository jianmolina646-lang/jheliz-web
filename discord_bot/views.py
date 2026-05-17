"""Webhook público para recibir interacciones de Discord.

Discord postea cada slash command / botón a esta vista. La firma se
verifica con la public key del bot; sin firma válida devolvemos 401.
"""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import interactions

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def interactions_webhook(request: HttpRequest) -> HttpResponse:
    """Endpoint público que Discord usa para slash commands y botones."""
    public_key = getattr(settings, "DISCORD_PUBLIC_KEY", "") or ""
    if not public_key:
        # Sin public key configurada, rechazamos para no exponer datos.
        return HttpResponse(status=503)

    signature = request.headers.get("X-Signature-Ed25519", "")
    timestamp = request.headers.get("X-Signature-Timestamp", "")
    body = request.body

    if not interactions.verify_signature(body, signature, timestamp, public_key):
        return HttpResponse("invalid signature", status=401)

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponse("bad payload", status=400)

    response = interactions.handle_interaction(payload)
    return JsonResponse(response, status=200)
