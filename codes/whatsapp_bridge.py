"""Private bridge used by the WhatsApp codes instance.

The bridge deliberately keeps authorization and IMAP access inside Django. The
WhatsApp worker can only relay a signed request; it never receives mailbox
credentials or unrestricted account data.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import imap_reader
from . import forwarding as _forwarding
from .models import AssignedEmail, BotState, CodeBotClient, CodeDelivery


def _matches_microsoft_forward(msg, account_email, *, trusted_authserv_id):
    """WhatsApp compatibility: exact Outlook/Hotmail identity, never body mentions.

    Keep this adapter scoped to the dedicated WhatsApp process until the shared
    IMAP image is upgraded. Telegram's running image is not changed.
    """
    target = (account_email or '').strip().lower()
    domain = target.rpartition('@')[2]
    if domain not in {'outlook.com', 'hotmail.com'}:
        return False
    if _forwarding._one_address(msg.get_all('From', [])) != target:
        return False
    if _forwarding._one_address(msg.get_all('X-Ms-Exchange-Inbox-Rules-Loop', [])) != target:
        return False
    submitted = msg.get_all('Auto-Submitted', [])
    if len(submitted) != 1 or str(submitted[0]).strip().lower() != 'auto-generated':
        return False
    trusted = (trusted_authserv_id or '').strip().lower()
    if not trusted or not re.fullmatch(r'[a-z0-9.-]+', trusted):
        return False
    seen = set()
    for header in msg.get_all('Authentication-Results', []):
        fields = _forwarding._auth_fields(str(header))
        if fields is None:
            return False
        identity = re.fullmatch(r'([a-z0-9.-]+)(?:\s+1)?', fields[0], re.I)
        if not identity or identity.group(1).lower() != trusted:
            continue
        if len(fields) < 2:
            return False
        for field in fields[1:]:
            result = _forwarding._auth_result(field)
            if result is None:
                return False
            method, status, properties = result
            if method not in {'dkim', 'dmarc'}:
                continue
            prop = 'header.d' if method == 'dkim' else 'header.from'
            if status != 'pass' or properties.get(prop) != domain:
                return False
            seen.add(method)
    if seen != {'dkim', 'dmarc'}:
        return False
    bodies = _forwarding._body_texts(msg)
    return bool(bodies) and all(_forwarding._original_recipient_matches(body, target) for body in bodies)


imap_reader.matches_outlook_forward = _matches_microsoft_forward

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_KINDS = {
    "/codigo": "signin_code", "/viaje": "temp_code", "/hogar": "household",
    "/clave": "password_reset", "/tv": "tv_signin",
    "/enlacetv": {"passwordless_signin", "tv_signin"},
}

_CLIENT_MENU = """*JHELIZ · CÓDIGOS*
🎬 *Netflix · ¿Qué necesitas?*
Elige una opción y copia su comando.

────────────
📂 *PRIMERO, ELIGE TU CUENTA*
Consulta tus correos asignados:
/miscorreos

El *1* de los ejemplos es el primer correo de esa lista.
Para el segundo correo, cambia *1* por *2*.

────────────
🔑 *INICIAR SESIÓN*
Obtener el código que Netflix te pide al ingresar:
/codigo 1

🧳 *ESTOY DE VIAJE*
Consultar el código de acceso temporal:
/viaje 1

🏠 *ACTUALIZAR EL HOGAR*
Obtener el enlace para continuar la actualización:
/hogar 1

🔐 *CONTRASEÑA*
Consultar el enlace de restablecimiento:
/clave 1

📺 *ACCESO EN TELEVISOR*
Consultar el acceso solicitado desde tu TV:
/tv 1

🔗 *ENLACE PARA EL TELEVISOR*
Consultar el enlace de inicio de sesión:
/enlacetv 1

────────────
💡 *ASÍ FUNCIONA*
1️⃣ Solicita primero el código o enlace en Netflix.
2️⃣ Envía aquí el comando con el número de tu cuenta.
3️⃣ Espera la respuesta y sigue las instrucciones.

Ejemplo para iniciar sesión con tu segundo correo:
/codigo 2

⏳ Envía una solicitud a la vez. Si necesitas repetirla, espera al menos 30 segundos.
🔒 Solo puedes consultar tus cuentas asignadas. No compartas códigos ni enlaces.

🏠 Volver a este menú:
/cmds"""

_ADMIN_MENU = """*JHELIZ · CENTRO DE CONTROL*
🛡️ *Administración de accesos*
━━━━━━━━━━━━━━

*👥 CLIENTES Y ACCESOS*
/clientes — Ver clientes registrados
/activar 51NUMERO — Habilitar acceso
/desactivar 51NUMERO — Suspender acceso

*📂 ASIGNACIÓN DE CUENTAS*
/asignar 51NUMERO correo@ejemplo.com
/quitar 51NUMERO correo@ejemplo.com

*⚙️ OPERACIÓN*
/limite 20 — Límite diario de consultas
/diagnostico — Revisar conexión al correo
/metricas — Consultas y entregas de hoy
/anuncio mensaje — Avisar a clientes activos

*Primeros pasos*
El cliente escribe /start. Después, activa su número y asígnale un correo.

Usa el número completo con código de país, sin espacios.
/cmds — Volver a este menú"""


def _reply(messages: list[dict]) -> JsonResponse:
    """Apply WhatsApp-native presentation without changing commands or data."""
    for message in messages:
        if not message["text"].startswith("*JHELIZ"):
            message["text"] = "*JHELIZ · CÓDIGOS*\n━━━━━━━━━━━━━━\n\n" + message["text"] + "\n\n_/cmds · Menú principal_"
    return JsonResponse({"messages": messages, "handled": True})


def _phone(value: str) -> str:
    value = str(value or "").strip().removeprefix("+")
    return value if re.fullmatch(r"[1-9][0-9]{7,14}", value) else ""


def _admins() -> set[str]:
    return {_phone(v) for v in getattr(settings, "WHATSAPP_CODES_ADMIN_NUMBERS", "").split(",") if _phone(v)}


def _client(phone: str, name: str = "") -> tuple[CodeBotClient, bool]:
    # Existing Telegram identities remain unchanged. WhatsApp identities use a
    # namespaced stable ID so the same tables, assignments and audit apply.
    client, created = CodeBotClient.objects.get_or_create(
        telegram_chat_id=f"wa:{phone}",
        defaults={"display_name": name[:120], "telegram_username": "whatsapp"},
    )
    if name and not client.display_name:
        client.display_name = name[:120]
        client.save(update_fields=["display_name"])
    return client, created


def _masked(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:2]}***{local[-1:]}@{domain}" if domain else email


def _access_message(email: str, payload: str, kind: str, is_code: bool) -> str:
    purposes = {
        "signin_code": "Inicio de sesión",
        "temp_code": "Acceso temporal de viaje",
        "household": "Actualización del hogar",
        "password_reset": "Restablecimiento de contraseña",
        "tv_signin": "Acceso en tu televisor",
        "passwordless_signin": "Inicio de sesión con enlace",
    }
    purpose = purposes.get(kind, "Acceso a tu cuenta")
    title = "CÓDIGO" if is_code else "ENLACE"
    displayed = f"```{payload}```" if is_code else payload
    steps = (
        "1️⃣ Copia el código tal como aparece.\n"
        "2️⃣ Vuelve a Netflix e introdúcelo en la pantalla que lo solicita."
        if is_code else
        "1️⃣ Abre el enlace de arriba.\n"
        "2️⃣ Sigue las indicaciones de Netflix para completar tu solicitud."
    )
    return (
        f"*JHELIZ · CÓDIGOS*\n🎬 *NETFLIX*\n\n"
        f"✅ *Tu {title.lower()} está listo*\n{purpose}\n\n"
        f"────────────\n📧 *Cuenta asignada*\n{_masked(email)}\n\n"
        f"{'🔑' if is_code else '🔗'} *TU {title}*\n{displayed}\n\n"
        f"────────────\n📲 *¿Cómo usarlo?*\n{steps}\n\n"
        "⏳ *Úsalo cuanto antes*\n"
        "Si Netflix indica que venció, solicita uno nuevo en Netflix y vuelve a consultar aquí.\n\n"
        "🔒 Este acceso es privado. No compartas ni reenvíes este mensaje.\n\n"
        "📂 Mis cuentas → /miscorreos\n🏠 Ver comandos → /cmds"
    )


def _limit_reached(client: CodeBotClient) -> bool:
    configured = int(getattr(settings, "CODES_DAILY_LIMIT", 20) or 0)
    custom = BotState.objects.filter(pk=3).values_list("daily_limit", flat=True).first()
    limit = configured if custom is None else int(custom)
    return bool(limit > 0 and CodeDelivery.objects.filter(client=client, created_at__date=timezone.localdate()).count() >= limit)


def _deliver(client: CodeBotClient, raw_email: str, kind) -> str:
    if int(cache.get(f"wa-codes:foreign:{client.pk}") or 0) >= int(getattr(settings, "CODES_FOREIGN_ATTEMPT_LIMIT", 3)):
        return "Consultas bloqueadas temporalmente. Contacta al administrador."
    email = raw_email.strip().lower()
    assigned = set(client.emails.values_list("email", flat=True))
    if not _EMAIL.match(email):
        return "Indica un correo asignado. Ejemplo: /codigo correo@ejemplo.com"
    if email not in assigned:
        key = f"wa-codes:foreign:{client.pk}"
        attempts = int(cache.get(key) or 0) + 1
        cache.set(key, attempts, timeout=int(getattr(settings, "CODES_SECURITY_BLOCK_SECONDS", 900)))
        return "Ese correo no está asignado a tu cuenta."
    if _limit_reached(client):
        return "Alcanzaste el límite diario de consultas. Contacta al administrador."
    if not cache.add(f"wa-codes:cooldown:{client.pk}", True, timeout=30):
        return "⏳ *Una consulta a la vez*\n\nEspera 30 segundos antes de volver a consultar. Después, envía el comando de tu cuenta."
    try:
        result = imap_reader.fetch_latest_for_email(email, kind=kind)
    except Exception:
        return "⚠️ *No pudimos consultar el correo*\n\nEspera un minuto y vuelve a enviar tu comando.\nSi el problema continúa, contacta al administrador."
    expected = {kind} if isinstance(kind, str) else set(kind)
    if not result or result.kind not in expected or not result.has_payload:
        CodeDelivery.objects.create(client=client, email=email, kind=kind if isinstance(kind, str) else "tv", found=False)
        return f"📨 *Todavía no encontramos tu acceso*\n🎬 Netflix\n\n📧 *Cuenta asignada*\n{_masked(email)}\n\n*¿Qué puedes hacer?*\n1️⃣ Solicita el código o enlace en Netflix.\n2️⃣ Espera al menos 30 segundos antes de volver a consultar aquí.\n\nNo necesitas enviar varios comandos seguidos."
    payload = result.code or result.action_url
    fingerprint = hashlib.sha256(payload.encode()).hexdigest()
    duplicate = CodeDelivery.objects.filter(client=client, email=email, payload_fingerprint=fingerprint, found=True, created_at__gte=timezone.now()-timedelta(hours=24)).exists()
    CodeDelivery.objects.create(client=client, email=email, kind=result.kind, found=not duplicate, duplicate=duplicate, payload_fingerprint=fingerprint)
    if duplicate:
        return "🔁 *Este acceso ya fue entregado*\n\nRevisa el mensaje anterior de este chat.\nSi Netflix ya no lo acepta, solicita un código o enlace nuevo en Netflix y vuelve a consultar aquí.\n\n🔒 No compartas tus códigos ni enlaces."
    client.touch()
    return _access_message(email, payload, result.kind, bool(result.code))


def _admin(phone: str, text: str) -> list[dict]:
    cmd, _, arg = text.partition(" ")
    if cmd == "/clientes":
        items = CodeBotClient.objects.filter(telegram_chat_id__startswith="wa:").order_by("-created_at")[:30]
        return [{"to": phone, "text": "Clientes WhatsApp:\n" + ("\n".join(f"{c.telegram_chat_id[3:]} · {'Activo' if c.is_active else 'Pendiente'} · {c.emails.count()} correo(s)" for c in items) or "Sin clientes registrados.")}]
    if cmd in {"/activar", "/desactivar"}:
        target = _phone(arg)
        client = CodeBotClient.objects.filter(telegram_chat_id=f"wa:{target}").first()
        if not client:
            return [{"to": phone, "text": "Ese cliente debe escribir /start primero."}]
        client.is_active = cmd == "/activar"; client.save(update_fields=["is_active"])
        return [{"to": phone, "text": f"Cliente {target} {'activado' if client.is_active else 'desactivado'}."}, {"to": target, "text": "Tu acceso al bot de códigos fue " + ("activado." if client.is_active else "desactivado.")}]
    if cmd in {"/asignar", "/quitar"}:
        parts = arg.split()
        if len(parts) != 2 or not _EMAIL.match(parts[1]):
            return [{"to": phone, "text": f"Uso: {cmd} 51NUMERO correo@ejemplo.com"}]
        target, email = _phone(parts[0]), parts[1].lower()
        client = CodeBotClient.objects.filter(telegram_chat_id=f"wa:{target}").first()
        if not client:
            return [{"to": phone, "text": "Ese cliente debe escribir /start primero."}]
        if cmd == "/asignar":
            AssignedEmail.objects.get_or_create(client=client, email=email)
            return [{"to": phone, "text": "Correo asignado."}, {"to": target, "text": "Se te asignó una cuenta. Escribe /miscorreos."}]
        AssignedEmail.objects.filter(client=client, email=email).delete()
        return [{"to": phone, "text": "Correo retirado."}]
    if cmd == "/limite":
        if not arg.isdigit(): return [{"to": phone, "text": "Uso: /limite 20"}]
        if len(arg)>5 or int(arg)>10000: return [{"to": phone, "text": "El límite debe estar entre 0 y 10000."}]
        BotState.objects.update_or_create(pk=3, defaults={"daily_limit": int(arg)})
        return [{"to": phone, "text": "Límite diario actualizado."}]
    if cmd == "/metricas":
        today = timezone.localdate()
        records = CodeDelivery.objects.filter(client__telegram_chat_id__startswith="wa:", created_at__date=today)
        return [{"to": phone, "text": f"Métricas WhatsApp de hoy\nSolicitudes: {records.count()}\nEntregadas: {records.filter(found=True).count()}"}]
    if cmd == "/diagnostico":
        checks = imap_reader.health_check()
        return [{"to": phone, "text": "IMAP: " + ("OK" if checks and all(c.get("ok") for c in checks) else "Revisar conexión")}]
    if cmd == "/anuncio" and arg.strip():
        targets = [c.telegram_chat_id for c in CodeBotClient.objects.filter(telegram_chat_id__startswith="wa:", is_active=True) if c.has_access]
        return [{"to": value[3:], "text": "Aviso Jheliz:\n\n" + arg.strip()} for value in targets] + [{"to": phone, "text": "Anuncio procesado."}]
    return [{"to": phone, "text": _ADMIN_MENU}]


@csrf_exempt
@require_POST
def whatsapp_codes(request: HttpRequest) -> JsonResponse:
    secret = getattr(settings, "WHATSAPP_CODES_BRIDGE_SECRET", "")
    body = request.body
    if len(body)>12000:
        return JsonResponse({"detail":"invalid"},status=400)
    if not secret or not hmac.compare_digest(request.headers.get("X-Codes-Signature", ""), hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()):
        return JsonResponse({"detail": "forbidden"}, status=403)
    try:
        data = json.loads(body)
        if not isinstance(data, dict): raise ValueError()
        phone = _phone(data.get("phone")); text = str(data.get("text") or "").strip(); name = str(data.get("name") or "")
        if abs(time.time()-float(data.get("timestamp",0)))>60: raise ValueError()
        nonce = str(data.get("request_id", ""))
        if not re.fullmatch(r"[a-f0-9-]{36}", nonce): raise ValueError()
    except (TypeError, ValueError):
        return JsonResponse({"detail": "invalid"}, status=400)
    if data.get("action") == "export_assignments":
        if not cache.add("wa-codes:request:"+nonce, True, timeout=120):
            return JsonResponse({"detail": "duplicate"}, status=409)
        records = []
        for client in CodeBotClient.objects.filter(telegram_chat_id__startswith="wa:").prefetch_related("emails").order_by("pk"):
            status = "Vencido" if client.is_expired else ("Activo" if client.is_active else "Inactivo")
            for assigned in list(client.emails.all()) or [None]:
                records.append({
                    "id": f"wa:{client.pk}:email:{assigned.pk}" if assigned else f"wa:{client.pk}:unassigned",
                    "phone": client.telegram_chat_id[3:], "name": client.display_name,
                    "email": assigned.email if assigned else "", "status": status,
                    "registered_at": client.created_at.isoformat(),
                    "assigned_at": assigned.created_at.isoformat() if assigned else "",
                    "expires_at": client.expires_at.isoformat() if client.expires_at else "",
                })
        return JsonResponse({"records": records, "schema": 1})
    if not phone or not text.startswith("/"):
        return JsonResponse({"messages": [], "handled": False})
    if not cache.add("wa-codes:request:"+nonce, True, timeout=120):
        return JsonResponse({"detail":"duplicate"},status=409)
    if phone in _admins():
        return _reply(_admin(phone, text))
    client, created = _client(phone, name)
    cmd, _, arg = text.lower().partition(" ")
    if cmd == "/start":
        status = "🟢 *Acceso activo*\n\n📂 /miscorreos — Tus cuentas asignadas\n🔐 /cmds — Todos los códigos y enlaces\n\nPara comenzar, solicita el código en Netflix y luego consulta aquí." if client.has_access else "🟠 *Acceso pendiente o vencido*\n\nTu número está registrado. Contacta al administrador para revisar tu acceso y asignarte un correo."
        return _reply([{"to": phone, "text": "*JHELIZ · CÓDIGOS*\n🎬 *Bienvenido a tu espacio Netflix*\n━━━━━━━━━━━━━━\n\nTus códigos y enlaces, desde este chat.\n\n"+status+"\n\n🔒 Atención exclusiva para tus cuentas asignadas."}])
    if not client.has_access:
        return _reply([{"to": phone, "text": "🟠 *Acceso no disponible*\n\nTu acceso no está activo o venció. Contacta al administrador."}])
    if cmd in {"/miscorreos", "/cmds"}:
        emails = list(client.emails.values_list("email", flat=True))
        text_out = "📂 *Tus correos asignados*\n\n" + ("\n".join(f"*{i+1}.* {_masked(e)}" for i,e in enumerate(emails)) + "\n\nElige por número: /codigo 1" if emails else "Aún no tienes correos asignados.\nPide al administrador que asigne tu cuenta.") if cmd == "/miscorreos" else _CLIENT_MENU
        return _reply([{"to": phone, "text": text_out}])
    if cmd in _KINDS:
        emails = list(client.emails.values_list("email", flat=True))
        email = arg.strip() or (emails[0] if len(emails) == 1 else "")
        if email.isdigit() and 1<=int(email)<=len(emails): email=emails[int(email)-1]
        return _reply([{"to": phone, "text": _deliver(client, email, _KINDS[cmd])}])
    return _reply([{"to": phone, "text": "💬 Escribe /cmds para ver los comandos disponibles."}])
