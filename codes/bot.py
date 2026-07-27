"""Bot de Telegram de códigos (long polling).

Flujo:

- ``/start``: registra al cliente (queda pendiente) y le muestra su chat id.
  Avisa al admin para que lo active y le asigne correos desde el panel.
- ``/miscorreos``: lista los correos asignados como botones.
- El cliente toca un correo (o lo escribe) → el bot lee la casilla central
  y devuelve el último código / link de "Actualizar Hogar" de Netflix.

Usa su propio token (``TELEGRAM_CODES_BOT_TOKEN``), separado del bot principal.
"""

from __future__ import annotations

import html
import logging
import re
import threading
import time
from typing import Any, Iterable

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from . import imap_reader
from .models import AssignedEmail, BotState, CodeBotClient, CodeDelivery
from .premium_emoji import custom_emoji_ids, emoji_id
from .premium_emoji import render as render_premium_emojis
from .premium_emoji import without_custom_emoji

logger = logging.getLogger(__name__)

# Pausa antes del único reintento cuando Gmail falla/responde lento.
_RETRY_SLEEP = 1.0
MAX_EMAIL_BUTTONS = 10

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

# Marca visible del bot en todos los mensajes.
BRAND = "TEAM JHELIZ"

# Los comandos del cliente -> tipo de correo de Netflix que entregan.
# Telegram no permite tildes ni mayúsculas en los comandos, así que el
# comando real es sin tilde (/codigo, /clave) pero el cliente lo escribe igual.
COMMAND_KINDS: dict[str, str] = {
    "/codigo": "signin_code",
    "/enlacesesion": "passwordless_signin",
    "/viaje": "temp_code",
    "/hogar": "household",
    "/clave": "password_reset",
    "/tv": "tv_signin",
}

# Etiqueta corta de cada tipo, para botones y mensajes.
KIND_LABELS: dict[str, str] = {
    "signin_code": "🔑 Código de inicio de sesión",
    "passwordless_signin": "🔗 Inicio sin contraseña",
    "temp_code": "✈️ Código de acceso temporal (viaje)",
    "household": "🏠 Actualizar Hogar",
    "password_reset": "🔒 Restablecer contraseña",
    "tv_signin": "📺 Activar Netflix en tu TV",
}

# Botones del menú fijo (teclado abajo del chat) -> comando equivalente.
MENU_BUTTONS: dict[str, str] = {
    "🔑 código": "/codigo",
    "✈️ viaje": "/viaje",
    "🏠 hogar": "/hogar",
    "🔒 clave": "/clave",
    "📺 activar tv": "/tv",
    "📋 mis correos": "/miscorreos",
    "❓ ayuda": "/cmds",
    "código": "/codigo",
    "viaje": "/viaje",
    "hogar": "/hogar",
    "clave": "/clave",
    "activar tv": "/tv",
    "mis correos": "/miscorreos",
}


# ---------- Configuración ----------

def _token() -> str:
    return getattr(settings, "TELEGRAM_CODES_BOT_TOKEN", "") or ""


def _admin_chat_id() -> str:
    return str(getattr(settings, "TELEGRAM_CODES_ADMIN_CHAT_ID", "") or "")


def _is_admin(chat_id) -> bool:
    admin = _admin_chat_id()
    return bool(admin) and str(chat_id) == admin


def is_configured() -> bool:
    return bool(_token())


# ---------- API low-level ----------

def _call(method: str, **payload) -> dict:
    token = _token()
    if not token:
        raise RuntimeError("TELEGRAM_CODES_BOT_TOKEN no configurado")
    url = TELEGRAM_API.format(token=token, method=method)
    resp = requests.post(url, json=payload, timeout=30)
    try:
        data = resp.json()
    except ValueError:
        data = {"ok": False, "description": resp.text}
    if not data.get("ok"):
        logger.warning("Telegram(codes) %s falló: %s", method, data)
    return data


def _build_reply_markup(buttons: Iterable[Iterable[dict]] | None) -> dict | None:
    if not buttons:
        return None
    return {"inline_keyboard": [[dict(b) for b in row] for row in buttons]}


def _without_button_styling(markup: dict) -> dict:
    """Fallback para clientes/servidores que aún no aceptan estilos nuevos."""
    clean: dict = {}
    for keyboard_key in ("keyboard", "inline_keyboard"):
        if keyboard_key in markup:
            clean[keyboard_key] = [
                [
                    {
                        key: value
                        for key, value in button.items()
                        if key not in {"style", "icon_custom_emoji_id"}
                    }
                    for button in row
                ]
                for row in markup[keyboard_key]
            ]
    for key, value in markup.items():
        if key not in {"keyboard", "inline_keyboard"}:
            clean[key] = value
    return clean


def _menu_keyboard() -> dict:
    """Teclado fijo (persistente) con las acciones principales."""
    def button(text: str, fallback: str, style: str) -> dict:
        item = {"text": text, "style": style}
        custom_id = emoji_id(fallback)
        if custom_id:
            item["icon_custom_emoji_id"] = custom_id
        return item

    return {
        "keyboard": [
            [
                button("Código", "🔑", "primary"),
                button("Viaje", "✈️", "primary"),
            ],
            [
                button("Hogar", "🏠", "success"),
                button("Clave", "🔒", "danger"),
            ],
            [
                button("Activar TV", "📺", "success"),
                button("Mis correos", "📋", "primary"),
            ],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def send_message(
    chat_id: str | int,
    text: str,
    buttons: Iterable[Iterable[dict]] | None = None,
    menu: bool = False,
) -> dict:
    rendered_text = render_premium_emojis(text)
    payload: dict[str, Any] = {
        "chat_id": str(chat_id),
        "text": rendered_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    markup = _build_reply_markup(buttons)
    if markup:
        payload["reply_markup"] = markup
    elif menu:
        payload["reply_markup"] = _menu_keyboard()
    result = _call("sendMessage", **payload)
    # Un ID incorrecto o una cuenta sin permiso no debe dejar al cliente sin
    # respuesta: se reintenta una vez con los emojis Unicode originales.
    if not result.get("ok") and rendered_text != text:
        payload["text"] = without_custom_emoji(rendered_text)
        result = _call("sendMessage", **payload)
    if not result.get("ok") and payload.get("reply_markup"):
        payload["reply_markup"] = _without_button_styling(payload["reply_markup"])
        return _call("sendMessage", **payload)
    return result


def edit_message(
    chat_id: str | int,
    message_id: int,
    text: str,
    buttons: Iterable[Iterable[dict]] | None = None,
) -> dict:
    """Actualiza un mensaje inline y conserva fallback a emojis Unicode."""
    rendered_text = render_premium_emojis(text)
    payload: dict[str, Any] = {
        "chat_id": str(chat_id),
        "message_id": message_id,
        "text": rendered_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": _build_reply_markup(buttons) or {"inline_keyboard": []},
    }
    result = _call("editMessageText", **payload)
    if not result.get("ok") and rendered_text != text:
        payload["text"] = without_custom_emoji(rendered_text)
        result = _call("editMessageText", **payload)
    if not result.get("ok") and payload.get("reply_markup"):
        payload["reply_markup"] = _without_button_styling(payload["reply_markup"])
        result = _call("editMessageText", **payload)
    description = str(result.get("description") or "").lower()
    if not result.get("ok") and "message is not modified" not in description:
        return send_message(chat_id, text, buttons=buttons)
    return result


def send_banner(chat_id: str | int, caption: str = "") -> bool:
    """Envía el banner de la marca (si existe el archivo). Devuelve True si salió."""
    path = getattr(settings, "CODES_BOT_BANNER", "") or ""
    if not path:
        return False
    token = _token()
    if not token:
        return False
    try:
        with open(path, "rb") as fh:
            url = TELEGRAM_API.format(token=token, method="sendPhoto")
            data: dict[str, Any] = {"chat_id": str(chat_id)}
            if caption:
                data["caption"] = caption
                data["parse_mode"] = "HTML"
            resp = requests.post(url, data=data, files={"photo": fh}, timeout=30)
        return bool(resp.ok and resp.json().get("ok"))
    except Exception:
        logger.exception("No se pudo enviar el banner")
        return False


def answer_callback_query(callback_query_id: str, text: str = "") -> dict:
    payload: dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    return _call("answerCallbackQuery", **payload)


def _delete_message_safely(chat_id: str | int, message_id: int) -> None:
    try:
        _call("deleteMessage", chat_id=str(chat_id), message_id=message_id)
    except Exception:
        logger.exception("No se pudo eliminar el mensaje sensible %s", message_id)


def _schedule_sensitive_deletion(
    chat_id: str | int,
    *,
    send_result: dict | None = None,
    message_id: int | None = None,
) -> None:
    """Programa el borrado sin bloquear el long polling del bot."""
    ttl = int(getattr(settings, "CODES_SENSITIVE_MESSAGE_TTL_SECONDS", 600) or 0)
    if message_id is None and isinstance(send_result, dict):
        message_id = (send_result.get("result") or {}).get("message_id")
    if ttl <= 0 or message_id is None:
        return
    timer = threading.Timer(
        ttl, _delete_message_safely, args=(str(chat_id), int(message_id))
    )
    timer.daemon = True
    timer.start()


# ---------- Helpers de dominio ----------

def _get_or_create_client(chat_id: str, username: str, name: str) -> tuple[CodeBotClient, bool]:
    client, created = CodeBotClient.objects.get_or_create(
        telegram_chat_id=str(chat_id),
        defaults={"telegram_username": username or "", "display_name": name or ""},
    )
    # Mantené el username/nombre actualizados.
    update_fields: list[str] = []
    if username and client.telegram_username != username:
        client.telegram_username = username
        update_fields.append("telegram_username")
    if name and not client.display_name:
        client.display_name = name
        update_fields.append("display_name")
    # El admin queda activo siempre: nunca ve el mensaje de "pasáselo al admin".
    if _is_admin(chat_id) and not client.is_active:
        client.is_active = True
        update_fields.append("is_active")
    if update_fields:
        client.save(update_fields=update_fields)
    return client, created


def _has_access(client: CodeBotClient) -> bool:
    return _is_admin(client.telegram_chat_id) or client.has_access


def _expired_message() -> str:
    return (
        "⏳ <b>Tu acceso venció.</b>\n"
        "Contactá al admin para renovarlo y seguir recibiendo tus códigos.\n"
        f"👑 <b>{BRAND}</b>"
    )


def _alert_admin(key: str, text: str, ttl: int = 3600) -> None:
    """Avisa al admin, con anti-repetición por ``key`` durante ``ttl`` seg."""
    admin = _admin_chat_id()
    if not admin:
        return
    cache_key = f"codesbot:alert:{key}"
    if cache.get(cache_key):
        return
    cache.set(cache_key, 1, timeout=ttl)
    try:
        send_message(admin, text)
    except Exception:
        logger.exception("No se pudo alertar al admin")


def _daily_limit() -> int:
    return int(getattr(settings, "CODES_DAILY_LIMIT", 20) or 0)


def _security_block_key(client: CodeBotClient) -> str:
    return f"codesbot:security-block:{client.telegram_chat_id}"


def _is_security_blocked(client: CodeBotClient) -> bool:
    return bool(cache.get(_security_block_key(client)))


def _record_foreign_attempt(client: CodeBotClient, email: str) -> None:
    block_seconds = int(
        getattr(settings, "CODES_SECURITY_BLOCK_SECONDS", 900) or 900
    )
    attempt_key = f"codesbot:foreign-attempts:{client.telegram_chat_id}"
    attempts = int(cache.get(attempt_key) or 0) + 1
    cache.set(attempt_key, attempts, timeout=block_seconds)
    limit = int(getattr(settings, "CODES_FOREIGN_ATTEMPT_LIMIT", 3) or 3)
    if attempts < limit:
        return
    cache.set(_security_block_key(client), 1, timeout=block_seconds)
    _alert_admin(
        f"security-block:{client.telegram_chat_id}",
        "🚨 <b>Cliente bloqueado temporalmente</b>\n"
        f"{html.escape(str(client))} intentó consultar {attempts} veces cuentas "
        "no asignadas. Último intento: "
        f"<code>{html.escape(_mask_email(email))}</code>.\n"
        f"Bloqueo aplicado por {max(1, block_seconds // 60)} minutos.",
        ttl=block_seconds,
    )


def _record_tv_activation_request(client: CodeBotClient, email: str) -> None:
    key = f"codesbot:tv-activation:{client.telegram_chat_id}"
    count = int(cache.get(key) or 0) + 1
    cache.set(key, count, timeout=600)
    if count >= 3:
        _alert_admin(
            f"tv-burst:{client.telegram_chat_id}",
            "⚠️ <b>Varias activaciones TV seguidas</b>\n"
            f"{html.escape(str(client))} solicitó {count} activaciones en menos "
            f"de 10 minutos. Última cuenta: "
            f"<code>{html.escape(_mask_email(email))}</code>.",
            ttl=600,
        )


def _over_daily_limit(client: CodeBotClient) -> bool:
    limit = _daily_limit()
    if limit <= 0 or _is_admin(client.telegram_chat_id):
        return False
    today = timezone.localdate()
    count = CodeDelivery.objects.filter(
        client=client, created_at__date=today
    ).count()
    if count < limit:
        return False
    _alert_admin(
        f"limit:{client.telegram_chat_id}:{today}",
        f"⚠️ <b>Límite diario alcanzado</b>\n"
        f"El cliente {html.escape(str(client))} ya hizo {count} pedidos hoy "
        f"(límite {limit}). El bot dejó de responderle por hoy.",
        ttl=6 * 3600,
    )
    return True


def _assigned_emails(client: CodeBotClient) -> list[str]:
    return list(client.emails.values_list("email", flat=True))


def _mask_email(email: str) -> str:
    """Oculta parte del usuario sin perder suficiente contexto para reconocerlo."""
    local, separator, domain = (email or "").partition("@")
    if not separator:
        return email
    if len(local) <= 4:
        masked_local = f"{local[:1]}•••"
    else:
        hidden = "•" * max(3, min(8, len(local) - 5))
        masked_local = f"{local[:3]}{hidden}{local[-2:]}"
    return f"{masked_local}@{domain}"


def _recent_emails(client: CodeBotClient, limit: int = 5) -> list[str]:
    assigned = set(_assigned_emails(client))
    recent: list[str] = []
    rows = CodeDelivery.objects.filter(client=client).values_list("email", flat=True)
    for email in rows:
        if email in assigned and email not in recent:
            recent.append(email)
        if len(recent) >= limit:
            break
    return recent


def _email_buttons(
    emails: list[str],
    kind: str | None = None,
    index_source: list[str] | None = None,
    icon_fallback: str | None = None,
    style: str | None = None,
) -> list[list[dict]]:
    """Botones para elegir un correo.

    El ``callback_data`` usa el índice del correo (no el correo entero) para
    no pasarse del límite de 64 bytes de Telegram. Si se pasa ``kind``, al
    tocar el botón se entrega ese tipo directamente; si no, se muestra el
    selector de tipo (``pick:<idx>``).
    """
    rows: list[list[dict]] = []
    source = index_source or emails
    for local_idx, e in enumerate(emails):
        idx = source.index(e) if index_source is not None else local_idx
        data = f"c:{kind}:{idx}" if kind else f"pick:{idx}"
        button = {"text": _mask_email(e), "callback_data": data}
        if icon_fallback:
            custom_id = emoji_id(icon_fallback)
            if custom_id:
                button["icon_custom_emoji_id"] = custom_id
        if style:
            button["style"] = style
        rows.append([button])
    return rows


def _tv_email_buttons(
    emails: list[str], index_source: list[str] | None = None
) -> list[list[dict]]:
    source = index_source or emails
    rows = []
    for local_idx, email in enumerate(emails):
        idx = source.index(email) if index_source is not None else local_idx
        rows.append(
            [
                {
                    "text": _mask_email(email),
                    "callback_data": f"tvmail:{idx}",
                    "style": "primary",
                    "icon_custom_emoji_id": emoji_id("📨"),
                }
            ]
        )
    return rows


def _kind_buttons(idx: int) -> list[list[dict]]:
    """Las 4 opciones de tipo para un correo (por índice)."""
    styles = {
        "signin_code": ("Código de inicio de sesión", "🔑", "primary"),
        "passwordless_signin": ("Inicio sin contraseña", "📧", "success"),
        "temp_code": ("Acceso temporal (viaje)", "✈️", "primary"),
        "household": ("Actualizar Hogar", "🏠", "success"),
        "password_reset": ("Restablecer contraseña", "🔒", "danger"),
        "tv_signin": ("Activar Netflix en tu TV", "📺", "success"),
    }
    rows = []
    for kind in COMMAND_KINDS.values():
        text, fallback, style = styles[kind]
        button = {
            "text": text,
            "callback_data": f"c:{kind}:{idx}",
            "style": style,
        }
        custom_id = emoji_id(fallback)
        if custom_id:
            button["icon_custom_emoji_id"] = custom_id
        rows.append([button])
    rows.append(
        [{"text": "⬅️ Volver", "callback_data": "back:emails", "style": "primary"}]
    )
    return rows


NETFLIX_TV_ACTIVATION_URL = "https://www.netflix.com/tv8"


def _tv_activation_message() -> str:
    return "\n".join([
        "\u2728 <b>\ud83d\udcfa Activar Netflix en tu TV</b>",
        "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
        "\ud83d\udcfa Si tu TV ya muestra un c\u00f3digo, ingresalo ac\u00e1: "
        f'<a href="{NETFLIX_TV_ACTIVATION_URL}">P\u00e1gina para activar la TV</a>',
        "(inici\u00e1 sesi\u00f3n con la cuenta y pon\u00e9 el c\u00f3digo de la TV).",
        "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
        f"\ud83d\udc51 <b>{BRAND}</b> \u00b7 gracias por tu compra",
    ])


def _cmd_tv(client: CodeBotClient) -> None:
    if not client.is_active:
        _send_welcome(client)
        return
    if not _has_access(client):
        send_message(client.telegram_chat_id, _expired_message())
        return
    send_message(client.telegram_chat_id, _tv_activation_message())


def _tv_email_confirmation(
    client: CodeBotClient,
    email: str,
    *,
    message_id: int | None = None,
) -> None:
    emails = _assigned_emails(client)
    email = (email or "").strip().lower()
    if email not in emails:
        # Reutiliza la validación, alerta y bloqueo progresivo centralizados.
        text = _deliver_code(client, email, kind="tv_signin")
        send_message(client.telegram_chat_id, text)
        return
    idx = emails.index(email)
    text = (
        "📨 <b>Confirmar activación por correo</b>\n\n"
        f"Cuenta: <code>{html.escape(_mask_email(email))}</code>\n"
        "Se buscará el enlace más reciente enviado por Netflix.\n\n"
        "¿Querés continuar?"
    )
    buttons = [
        [
            {
                "text": "Confirmar activación",
                "callback_data": f"tvconfirm:{idx}",
                "style": "success",
                "icon_custom_emoji_id": emoji_id("📨"),
            }
        ],
        [{"text": "Cancelar", "callback_data": "back:emails", "style": "danger"}],
    ]
    if message_id is not None:
        edit_message(client.telegram_chat_id, message_id, text, buttons=buttons)
    else:
        send_message(client.telegram_chat_id, text, buttons=buttons)


def _cmd_tv_email(client: CodeBotClient, arg: str) -> None:
    """Busca el enlace de activación TV enviado por email a una cuenta concreta."""
    chat_id = client.telegram_chat_id
    if not client.is_active:
        _send_welcome(client)
        return
    if not _has_access(client):
        send_message(chat_id, _expired_message())
        return
    emails = _assigned_emails(client)
    if not emails:
        _send_welcome(client)
        return

    email = (arg or "").strip().lower()
    if not email:
        if len(emails) == 1:
            email = emails[0]
        elif len(emails) <= MAX_EMAIL_BUTTONS:
            send_message(
                chat_id,
                "📨 Elegí la cuenta que recibió el enlace de activación:",
                buttons=_tv_email_buttons(emails),
            )
            return
        else:
            send_message(
                chat_id,
                f"Tenés <b>{len(emails)}</b> cuentas. Indicá exactamente cuál "
                "recibió el mensaje:\n"
                "<code>/enlacetv nombre@correo.com</code>",
            )
            return

    _tv_email_confirmation(client, email)


def _format_result(email: str, result) -> str:
    parts = [
        f"✨ <b>{html.escape(result.human_kind)}</b>",
        f"📧 <code>{html.escape(_mask_email(email))}</code>",
        "──────────────────",
    ]
    if result.code:
        parts.append(f"🔢 Código: <code>{html.escape(result.code)}</code>")
    if result.action_url:
        parts.append(
            f'🔗 <a href="{html.escape(result.action_url)}">Abrir en Netflix</a>'
        )
    if result.kind == "tv_signin":
        parts.append(
            f'📺 <a href="{NETFLIX_TV_ACTIVATION_URL}">Página para activar la TV</a>'
            " — iniciá sesión con la cuenta y poné el código que muestra la TV."
        )
    parts.append("──────────────────")
    parts.append("⏱ Suele vencer en ~15 min. Si no funciona, generá uno nuevo y volvé a pedirlo.")
    parts.append(f"👑 <b>{BRAND}</b> · gracias por tu compra")
    return "\n".join(parts)


def _result_cache_key(email: str, kind: str | None) -> str:
    return f"codesbot:res:{email}:{kind or 'any'}"


def _cooldown_key(chat_id: str) -> str:
    return f"codesbot:cd:{chat_id}"


def _on_cooldown(client: CodeBotClient) -> bool:
    """True si el cliente pidió hace muy poco (anti-spam / anti-bloqueo Gmail).

    El admin queda exento para poder probar sin esperas.
    """
    secs = getattr(settings, "CODES_COOLDOWN_SECONDS", 6)
    if secs <= 0 or str(client.telegram_chat_id) == _admin_chat_id():
        return False
    key = _cooldown_key(client.telegram_chat_id)
    if cache.get(key):
        return True
    cache.set(key, 1, timeout=secs)
    return False


def _deliver_code(client: CodeBotClient, email: str, kind: str | None = None) -> str:
    email = (email or "").strip().lower()
    if not _has_access(client):
        return _expired_message()
    if _is_security_blocked(client):
        return (
            "🛑 <b>Acceso temporalmente bloqueado</b>\n"
            "Detectamos varios intentos sobre cuentas no asignadas. Esperá "
            "15 minutos o contactá al administrador."
        )
    assigned = set(_assigned_emails(client))
    if email not in assigned:
        _record_foreign_attempt(client, email)
        _alert_admin(
            f"foreign:{client.telegram_chat_id}",
            f"🚨 <b>Pedido sospechoso</b>\n"
            f"El cliente {html.escape(str(client))} pidió un código del correo "
            f"<code>{html.escape(email)}</code>, que NO tiene asignado.",
        )
        return (
            f"⚠️ El correo <b>{html.escape(email)}</b> no está asignado a tu "
            "cuenta, así que no te corresponde. Si creés que es un error, "
            "escribile al admin."
        )
    if _over_daily_limit(client):
        return (
            "🛑 Alcanzaste el límite de pedidos por hoy.\n"
            "Si necesitás más códigos, escribile al admin."
        )
    if not imap_reader.is_configured():
        return "El servicio de códigos todavía no está configurado. Probá más tarde."

    # Mini-caché: si justo leímos este código hace unos segundos, lo
    # reusamos (toques repetidos al mismo botón) sin volver a Gmail.
    cache_key = _result_cache_key(email, kind)
    cached = cache.get(cache_key)
    if cached:
        client.touch()
        return cached

    # Anti-spam: si pide de más, evitamos golpear Gmail (que puede bloquear).
    if _on_cooldown(client):
        return (
            "⏳ Esperá unos segundos antes de pedir otro código y volvé a "
            "intentar (así no saturamos el correo)."
        )

    result = None
    for attempt in range(2):
        try:
            result = imap_reader.fetch_latest_for_email(email, kind=kind)
            break
        except Exception:
            logger.exception("Fallo leyendo IMAP para %s (intento %d)", email, attempt + 1)
            if attempt == 0:
                time.sleep(_RETRY_SLEEP)
                continue
            return "Hubo un problema leyendo el correo. Probá de nuevo en un minuto."
    if result is None or not result.has_payload:
        CodeDelivery.objects.create(
            client=client, email=email, kind=kind or "", found=False
        )
        if kind and kind in KIND_LABELS:
            que = f"<b>{html.escape(KIND_LABELS[kind])}</b>"
        else:
            que = "un código reciente"
        extra = ""
        if kind == "tv_signin":
            extra = (
                "\n\n📺 Si tu TV ya muestra un código, ingresalo acá: "
                f'<a href="{NETFLIX_TV_ACTIVATION_URL}">Página para activar la TV</a>'
                " (iniciá sesión con la cuenta y poné el código de la TV)."
            )
        return (
            f"No encontré {que} para <b>{html.escape(_mask_email(email))}</b>.\n"
            "Generá el correo desde Netflix y volvé a pedirlo en un minuto."
            + extra
        )
    client.touch()
    CodeDelivery.objects.create(
        client=client, email=email, kind=kind or "", found=True
    )
    msg = _format_result(email, result)
    ttl = getattr(settings, "CODES_RESULT_CACHE_SECONDS", 45)
    if ttl > 0:
        cache.set(cache_key, msg, timeout=ttl)
    return msg


def _cmd_code(client: CodeBotClient, kind: str, arg: str) -> None:
    """Procesa un comando que recupera un código o enlace por correo."""
    chat_id = client.telegram_chat_id
    if not client.is_active:
        _send_welcome(client)
        return
    if not _has_access(client):
        send_message(chat_id, _expired_message())
        return
    emails = _assigned_emails(client)
    if not emails:
        send_message(
            chat_id,
            "Tu cuenta está activa pero todavía no tenés correos asignados.\n"
            "El admin te los va a asignar en breve.",
        )
        return

    arg = (arg or "").strip().lower()
    if not arg:
        # Sin correo: si tiene uno solo, lo usamos; si tiene varios, que elija.
        if len(emails) == 1:
            arg = emails[0]
        else:
            if len(emails) > MAX_EMAIL_BUTTONS:
                send_message(
                    chat_id,
                    f"Tenés <b>{len(emails)}</b> correos asignados. Buscá primero "
                    "el que necesitás con:\n"
                    "<code>/buscar nombre@correo.com</code>",
                )
                return
            send_message(
                chat_id,
                f"¿De qué correo querés <b>{html.escape(KIND_LABELS[kind])}</b>?\n"
                "Elegí uno (o repetí el comando con el correo al lado):",
                buttons=_email_buttons(emails, kind=kind),
            )
            return

    result = send_message(chat_id, _deliver_code(client, arg, kind=kind))
    _schedule_sensitive_deletion(chat_id, send_result=result)


# ---------- Handlers ----------

def _handle_message(update: dict) -> None:
    msg = update.get("message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return
    text = (msg.get("text") or "").strip()
    from_user = msg.get("from") or {}
    username = from_user.get("username") or ""
    name = " ".join(
        p for p in [from_user.get("first_name"), from_user.get("last_name")] if p
    )

    client, created = _get_or_create_client(chat_id, username, name)

    # Botones del menú fijo: los traducimos al comando equivalente.
    menu_cmd = MENU_BUTTONS.get(text.lower())
    if menu_cmd:
        text = menu_cmd

    cmd, _, rest = text.partition(" ")
    cmd = cmd.lower().split("@", 1)[0]  # quita @botname si lo hubiera
    rest = rest.strip()

    if cmd == "/start":
        if created:
            _notify_admin_new(client)
        send_banner(chat_id)
        _send_welcome(client)
        return
    if cmd in ("/ayuda", "/help", "/cmds", "/comandos"):
        _send_commands_help(client)
        return
    if cmd == "/emojiid" and _is_admin(chat_id):
        ids = custom_emoji_ids(msg)
        if ids:
            send_message(
                chat_id,
                "IDs de emoji Premium encontrados:\n"
                + "\n".join(f"<code>{html.escape(custom_id)}</code>" for custom_id in ids),
            )
        else:
            send_message(
                chat_id,
                "Respondé con <code>/emojiid</code> a un mensaje que contenga "
                "el emoji Premium que querés usar.",
            )
        return
    if cmd == "/miscorreos":
        _send_email_menu(client)
        return
    if cmd == "/buscar":
        _cmd_search(client, rest)
        return
    if cmd == "/enlacetv":
        _cmd_tv_email(client, rest)
        return

    # Comandos de admin (solo para el chat del admin).
    if _is_admin(chat_id) and cmd in (
        "/clientes", "/asignar", "/quitar", "/anuncio", "/activar", "/desactivar"
    ):
        _handle_admin_command(chat_id, cmd, rest)
        return

    # /tv responde directo con la página de activación (sin leer correos).
    if cmd in COMMAND_KINDS and COMMAND_KINDS[cmd] == "tv_signin":
        _cmd_tv(client)
        return

    # Los 4 comandos de tipo de código (/codigo /viaje /hogar /clave).
    if cmd in COMMAND_KINDS:
        _cmd_code(client, COMMAND_KINDS[cmd], rest)
        return

    # ¿Escribió un correo a secas? Le mostramos el selector de tipo.
    if "@" in text and " " not in text:
        _offer_kinds_for_email(client, text)
        return

    _send_welcome(client)


def _handle_callback(update: dict) -> None:
    cq = update.get("callback_query") or {}
    data = cq.get("data") or ""
    cq_id = cq.get("id")
    callback_message = cq.get("message") or {}
    chat = callback_message.get("chat") or {}
    chat_id = chat.get("id")
    message_id = callback_message.get("message_id")
    from_user = cq.get("from") or {}
    if chat_id is None:
        return
    client, _ = _get_or_create_client(
        chat_id, from_user.get("username") or "", from_user.get("first_name") or ""
    )
    emails = _assigned_emails(client)
    if data.startswith("c:"):
        # c:<kind>:<idx> -> entregar ese tipo para el correo elegido.
        _, _, payload = data.partition(":")
        kind, _, idx_raw = payload.partition(":")
        if cq_id:
            answer_callback_query(cq_id, "Buscando…")
        try:
            idx = int(idx_raw)
        except ValueError:
            return
        if kind == "tv_signin":
            text = (
                _tv_activation_message()
                if _has_access(client)
                else _expired_message()
            )
            if message_id is not None:
                edit_message(chat_id, message_id, text)
            else:
                send_message(chat_id, text)
            return
        if 0 <= idx < len(emails):
            if message_id is not None:
                edit_message(
                    chat_id,
                    message_id,
                    "⏳ <b>Buscando el correo más reciente…</b>",
                )
            result_text = _deliver_code(client, emails[idx], kind=kind)
            if message_id is not None:
                edit_result = edit_message(chat_id, message_id, result_text)
                _schedule_sensitive_deletion(
                    chat_id,
                    send_result=edit_result,
                    message_id=(
                        None
                        if isinstance(edit_result, dict)
                        and (edit_result.get("result") or {}).get("message_id")
                        else message_id
                    ),
                )
            else:
                result = send_message(chat_id, result_text)
                _schedule_sensitive_deletion(chat_id, send_result=result)
        return
    if data == "back:emails":
        if cq_id:
            answer_callback_query(cq_id)
        recent = _recent_emails(client)
        if recent:
            text = (
                "📧 <b>Cuentas recientes</b>\n"
                "Elegí una o buscá otra con <code>/buscar nombre</code>."
            )
            buttons = _email_buttons(recent, index_source=emails)
        else:
            text = (
                "🔍 <b>Buscar una cuenta</b>\n"
                "Escribí <code>/buscar nombre@correo.com</code>."
            )
            buttons = None
        if message_id is not None:
            edit_message(chat_id, message_id, text, buttons=buttons)
        else:
            send_message(chat_id, text, buttons=buttons)
        return
    if data.startswith("tvmail:"):
        if cq_id:
            answer_callback_query(cq_id)
        try:
            idx = int(data.split(":", 1)[1])
        except ValueError:
            return
        if 0 <= idx < len(emails):
            _tv_email_confirmation(
                client, emails[idx], message_id=message_id
            )
        return
    if data.startswith("tvconfirm:"):
        if cq_id:
            answer_callback_query(cq_id, "Buscando…")
        try:
            idx = int(data.split(":", 1)[1])
        except ValueError:
            return
        if 0 <= idx < len(emails):
            _record_tv_activation_request(client, emails[idx])
            if message_id is not None:
                edit_message(
                    chat_id,
                    message_id,
                    "⏳ <b>Buscando el enlace enviado por Netflix…</b>",
                )
            result_text = _deliver_code(client, emails[idx], kind="tv_signin")
            if message_id is not None:
                edit_result = edit_message(chat_id, message_id, result_text)
                _schedule_sensitive_deletion(
                    chat_id,
                    send_result=edit_result,
                    message_id=(
                        None
                        if isinstance(edit_result, dict)
                        and (edit_result.get("result") or {}).get("message_id")
                        else message_id
                    ),
                )
            else:
                result = send_message(chat_id, result_text)
                _schedule_sensitive_deletion(chat_id, send_result=result)
        return
    if data.startswith("pick:"):
        # pick:<idx> -> mostrar las 4 opciones de tipo para ese correo.
        if cq_id:
            answer_callback_query(cq_id)
        try:
            idx = int(data.split(":", 1)[1])
        except ValueError:
            return
        if 0 <= idx < len(emails):
            text = (
                f"📧 <b>{html.escape(_mask_email(emails[idx]))}</b>\n"
                "¿Qué necesitás?"
            )
            if message_id is not None:
                edit_message(chat_id, message_id, text, buttons=_kind_buttons(idx))
            else:
                send_message(chat_id, text, buttons=_kind_buttons(idx))
        return
    if cq_id:
        answer_callback_query(cq_id)


def _send_welcome(client: CodeBotClient) -> None:
    chat_id = client.telegram_chat_id
    admin = _is_admin(chat_id)
    # El mensaje de "pedí activación" es solo para clientes, no para el admin.
    if not client.is_active and not admin:
        send_message(
            chat_id,
            f"👋 <b>¡Bienvenido al Bot de Códigos de {BRAND}!</b> ✨\n\n"
            "Acá vas a obtener al instante los códigos de tu cuenta de Netflix:\n"
            "🔑 inicio de sesión · ✈️ viaje · 🏠 Hogar · 🔒 contraseña · 📺 TV\n\n"
            "🔒 Tu acceso todavía <b>no está activado</b>.\n"
            f"Tu ID es <code>{html.escape(str(chat_id))}</code>.\n"
            "Enviáselo al admin para que te active y te asigne tus correos. "
            "En cuanto lo haga, te aviso por acá ✅",
        )
        return
    emails = _assigned_emails(client)
    if admin:
        send_message(
            chat_id,
            f"👋 <b>Hola, admin.</b> Bienvenido al Bot de Códigos de {BRAND}.\n\n"
            + _admin_help_text(),
            buttons=(
                _email_buttons(emails)
                if 0 < len(emails) <= MAX_EMAIL_BUTTONS
                else None
            ),
        )
        return
    if not emails:
        send_message(
            chat_id,
            "✅ <b>Tu cuenta está activada</b>, pero todavía no tenés correos asignados.\n"
            "El admin te los va a asignar en breve. Te aviso cuando estén listos 📩",
        )
        return
    if not _has_access(client):
        send_message(chat_id, _expired_message())
        return
    send_message(
        chat_id,
        f"✨ <b>{BRAND} · Códigos Netflix</b>\n\n"
        "Elegí una acción en el menú.\n"
        "Para encontrar una cuenta usá <code>/buscar nombre</code>.\n\n"
        "❓ Ayuda completa: <code>/cmds</code>",
        menu=True,
    )


def _send_commands_help(client: CodeBotClient) -> None:
    """Responde a /cmds: comandos de admin si es el admin, de cliente si no."""
    chat_id = client.telegram_chat_id
    if _is_admin(chat_id):
        send_message(chat_id, _admin_help_text())
        return
    if not client.is_active:
        _send_welcome(client)
        return
    emails = _assigned_emails(client)
    send_message(
        chat_id,
        _client_help_text(emails),
        buttons=_email_buttons(emails) if 0 < len(emails) <= MAX_EMAIL_BUTTONS else None,
    )


def _client_help_text(emails: list[str]) -> str:
    ejemplo = emails[0] if emails else "tucorreo@gmail.com"
    lines = [
        f"✨ <b>Bot de Códigos · {BRAND}</b>",
        "──────────────────",
        "Escribí el comando con tu correo al lado 👇",
        "",
        f"🔑 <code>/codigo {ejemplo}</code> — código de inicio de sesión",
        f"🔗 <code>/enlacesesion {ejemplo}</code> — enlace para iniciar sin contraseña",
        f"✈️ <code>/viaje {ejemplo}</code> — código de acceso temporal (de viaje)",
        f"🏠 <code>/hogar {ejemplo}</code> — link para actualizar Hogar",
        f"🔒 <code>/clave {ejemplo}</code> — link para restablecer contraseña",
        "📺 <code>/tv</code> — página para activar Netflix en tu TV",
        "📨 <code>/enlacetv correo</code> — buscar el enlace enviado por Netflix",
        "",
        "📋 <code>/miscorreos</code> — ver tus correos asignados",
        "🔍 <code>/buscar nombre@gmail.com</code> — encontrar un correo asignado",
        "❓ <code>/cmds</code> — ver esta ayuda",
    ]
    if not emails:
        lines.append("")
        lines.append("⏳ Todavía no tenés correos asignados; el admin te los asigna en breve.")
    elif len(emails) == 1:
        lines.append("")
        lines.append(
            "💡 Tenés un solo correo, así que podés mandar el comando solo "
            "(ej. <code>/codigo</code>) y te lo doy de esa cuenta."
        )
    elif len(emails) <= MAX_EMAIL_BUTTONS:
        lines.append("")
        lines.append("💡 También podés tocar un correo de abajo y elegir qué necesitás.")
    else:
        lines.append("")
        lines.append(
            f"💡 Tenés {len(emails)} correos. Encontrá rápidamente el que "
            "necesitás con <code>/buscar nombre</code>."
        )
    return "\n".join(lines)


def _admin_help_text() -> str:
    lines = [
        f"🛠 <b>Panel de administrador · {BRAND}</b>",
        "──────────────────",
        "👥 <code>/clientes</code> — lista de clientes (ID, usuario, correos)",
        "🔓 <code>/activar &lt;ID o @usuario&gt;</code> — activa el acceso (sin asignar correo aún)",
        "⏸ <code>/desactivar &lt;ID o @usuario&gt;</code> — pausa el acceso",
        "➕ <code>/asignar &lt;ID o @usuario&gt; &lt;correo&gt;</code> — asigna y activa",
        "➖ <code>/quitar &lt;ID o @usuario&gt; &lt;correo&gt;</code> — quita un correo",
        "📢 <code>/anuncio &lt;mensaje&gt;</code> — enviar un anuncio a todos los registrados",
        "",
        "— También tenés los comandos de cliente —",
        "🔑 /codigo · 🔗 /enlacesesion · ✈️ /viaje · 🏠 /hogar · 🔒 /clave · 📺 /tv · "
        "📋 /miscorreos · 🔍 /buscar",
    ]
    return "\n".join(lines)


def _offer_kinds_for_email(client: CodeBotClient, raw_email: str) -> None:
    chat_id = client.telegram_chat_id
    if not client.is_active:
        _send_welcome(client)
        return
    email = (raw_email or "").strip().lower()
    emails = _assigned_emails(client)
    if email not in set(emails):
        send_message(
            chat_id,
            f"⚠️ El correo <b>{html.escape(email)}</b> no está asignado a tu "
            "cuenta, así que no te corresponde. Si creés que es un error, "
            "escribile al admin.",
        )
        return
    idx = emails.index(email)
    send_message(
        chat_id,
        f"📧 <b>{html.escape(_mask_email(email))}</b>\n¿Qué necesitás?",
        buttons=_kind_buttons(idx),
    )


def _send_email_menu(client: CodeBotClient) -> None:
    emails = _assigned_emails(client)
    if not client.is_active or not emails:
        _send_welcome(client)
        return
    if len(emails) > MAX_EMAIL_BUTTONS:
        recent = _recent_emails(client)
        send_message(
            client.telegram_chat_id,
            f"📧 Tenés <b>{len(emails)}</b> correos asignados.\n\n"
            "Para encontrar uno escribí parte del nombre o el correo completo:\n"
            "<code>/buscar nombre@gmail.com</code>"
            + ("\n\nTus cuentas recientes:" if recent else ""),
            buttons=_email_buttons(recent, index_source=emails) if recent else None,
        )
        return
    send_message(
        client.telegram_chat_id,
        "Tus correos asignados. Tocá uno y elegí qué necesitás:",
        buttons=_email_buttons(emails),
    )


def _cmd_search(client: CodeBotClient, raw_query: str) -> None:
    """Busca únicamente dentro de los correos asignados al cliente."""
    chat_id = client.telegram_chat_id
    if not client.is_active:
        _send_welcome(client)
        return
    if not _has_access(client):
        send_message(chat_id, _expired_message())
        return

    emails = _assigned_emails(client)
    if not emails:
        _send_welcome(client)
        return

    search_key = f"codesbot:search:{client.telegram_chat_id}"
    if not _is_admin(chat_id) and cache.get(search_key):
        send_message(chat_id, "⏳ Esperá un momento antes de realizar otra búsqueda.")
        return
    cache.set(search_key, 1, timeout=2)

    query = (raw_query or "").strip().lower()
    if not query:
        send_message(
            chat_id,
            "🔍 Escribí una parte del correo que buscás.\n"
            "Ejemplo: <code>/buscar nombre@gmail.com</code>",
        )
        return
    if len(query) < 2:
        send_message(chat_id, "🔍 Escribí al menos 2 caracteres para buscar.")
        return

    matches = [email for email in emails if query in email.lower()]
    if not matches:
        send_message(
            chat_id,
            f"🔍 No encontré correos asignados que coincidan con "
            f"<code>{html.escape(query)}</code>.",
        )
        return
    if len(matches) == 1:
        _offer_kinds_for_email(client, matches[0])
        return

    visible = matches[:MAX_EMAIL_BUTTONS]
    extra = len(matches) - len(visible)
    detail = (
        f"\nMostrando los primeros {len(visible)}. Escribí una búsqueda más "
        "específica." if extra else ""
    )
    send_message(
        chat_id,
        f"🔍 Encontré <b>{len(matches)}</b> coincidencias. Elegí un correo:{detail}",
        buttons=_email_buttons(
            visible,
            index_source=emails,
            icon_fallback="🔍",
            style="primary",
        ),
    )


# ---------- Comandos de admin ----------

# Validación simple de correo (suficiente para el panel del bot).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _resolve_client(token: str) -> CodeBotClient | None:
    """Encuentra un cliente por chat_id numérico o por @usuario."""
    token = (token or "").strip()
    if not token:
        return None
    if token.startswith("@"):
        token = token[1:]
    qs = CodeBotClient.objects.all()
    if token.isdigit():
        return qs.filter(telegram_chat_id=token).first()
    return qs.filter(telegram_username__iexact=token).first()


def _handle_admin_command(chat_id, cmd: str, rest: str) -> None:
    if cmd == "/clientes":
        _admin_list_clients(chat_id)
    elif cmd == "/asignar":
        _admin_assign(chat_id, rest, add=True)
    elif cmd == "/quitar":
        _admin_assign(chat_id, rest, add=False)
    elif cmd == "/anuncio":
        _admin_broadcast(chat_id, rest)
    elif cmd in ("/activar", "/desactivar"):
        _admin_set_active(chat_id, rest, active=(cmd == "/activar"))


def _admin_set_active(chat_id, token: str, active: bool) -> None:
    """Activa o desactiva a un cliente sin tocar sus correos.

    Sirve para habilitar el acceso al bot aunque todavía no se le haya
    asignado ninguna cuenta.
    """
    accion = "activar" if active else "desactivar"
    token = (token or "").strip()
    if not token:
        send_message(
            chat_id,
            f"Uso: <code>/{accion} &lt;ID o @usuario&gt;</code>\n"
            f"Ej: <code>/{accion} 8761148983</code>",
        )
        return
    client = _resolve_client(token)
    if client is None:
        send_message(
            chat_id,
            f"No encontré un cliente con <code>{html.escape(token)}</code>.\n"
            "El cliente tiene que haber mandado <b>/start</b> al bot primero. "
            "Mirá <code>/clientes</code> para ver los IDs.",
        )
        return
    label = f"{client.display_name or 'cliente'} (<code>{html.escape(str(client.telegram_chat_id))}</code>)"
    if client.is_active == active:
        estado = "ya estaba activo" if active else "ya estaba desactivado"
        send_message(chat_id, f"{label} {estado}.")
        return
    client.is_active = active
    client.save(update_fields=["is_active"])
    if active:
        send_message(chat_id, f"✅ Activé a {label}. (Aún sin correos: asignale con <code>/asignar</code>.)")
        send_message(
            client.telegram_chat_id,
            "✅ <b>El admin activó tu acceso al bot.</b>\n"
            "En breve te asigna tus correos y vas a poder pedir /codigo, /viaje, /hogar, /clave o /tv.",
        )
    else:
        send_message(chat_id, f"⏸ Desactivé a {label}. Ya no puede pedir códigos hasta que lo reactives.")


def _admin_broadcast(chat_id, message: str) -> None:
    """Envía un anuncio a todos los que alguna vez hicieron /start.

    Excluye al propio admin (que recibe en cambio un resumen de entrega).
    """
    message = (message or "").strip()
    if not message:
        send_message(
            chat_id,
            "Uso: <code>/anuncio &lt;mensaje&gt;</code>\n"
            "Ej: <code>/anuncio Mañana renuevo las cuentas, aviso cuando esté listo.</code>",
        )
        return
    body = f"📢 <b>Anuncio · {BRAND}</b>\n\n" + html.escape(message)
    recipients = (
        CodeBotClient.objects.exclude(telegram_chat_id=str(chat_id))
        .exclude(telegram_chat_id="")
        .values_list("telegram_chat_id", flat=True)
    )
    sent = 0
    failed = 0
    for rid in recipients:
        try:
            resp = send_message(rid, body)
        except Exception:
            logger.exception("Anuncio: fallo enviando a %s", rid)
            failed += 1
            continue
        if resp.get("ok"):
            sent += 1
        else:
            failed += 1
    send_message(
        chat_id,
        "📣 <b>Anuncio enviado.</b>\n"
        f"✅ Entregados: <b>{sent}</b>\n"
        f"⚠️ Fallidos: <b>{failed}</b>"
        + ("\n\n(Los fallidos suelen ser clientes que bloquearon el bot.)" if failed else ""),
    )


def _admin_list_clients(chat_id) -> None:
    clients = CodeBotClient.objects.prefetch_related("emails").order_by("-created_at")
    if not clients:
        send_message(chat_id, "Todavía no hay clientes registrados en el bot.")
        return
    lines = ["👥 <b>Clientes del bot</b>:"]
    for c in clients:
        emails = list(c.emails.values_list("email", flat=True))
        uname = f"@{c.telegram_username}" if c.telegram_username else "(sin usuario)"
        estado = "✅" if c.is_active else "⏸"
        correos = ", ".join(emails) if emails else "—"
        lines.append(
            f"\n{estado} <b>{html.escape(c.display_name or 'cliente')}</b> "
            f"{html.escape(uname)}\n"
            f"   ID: <code>{html.escape(str(c.telegram_chat_id))}</code>\n"
            f"   Correos: {html.escape(correos)}"
        )
    lines.append(
        "\n\nUsá <code>/asignar &lt;ID o @usuario&gt; &lt;correo&gt;</code> "
        "para asignar."
    )
    send_message(chat_id, "".join(lines))


def _admin_assign(chat_id, rest: str, add: bool) -> None:
    accion = "asignar" if add else "quitar"
    parts = rest.split()
    if len(parts) < 2:
        send_message(
            chat_id,
            f"Uso: <code>/{accion} &lt;ID o @usuario&gt; &lt;correo&gt;</code>\n"
            f"Ej: <code>/{accion} 12345678 villalimalemon@gmail.com</code>",
        )
        return
    token, email = parts[0], parts[1].strip().lower()
    if not _EMAIL_RE.match(email):
        send_message(chat_id, f"⚠️ <b>{html.escape(email)}</b> no parece un correo válido.")
        return
    client = _resolve_client(token)
    if client is None:
        send_message(
            chat_id,
            f"No encontré un cliente con <code>{html.escape(token)}</code>.\n"
            "El cliente tiene que haber mandado <b>/start</b> al bot primero. "
            "Mirá <code>/clientes</code> para ver los IDs.",
        )
        return
    label = f"{client.display_name or 'cliente'} (<code>{html.escape(str(client.telegram_chat_id))}</code>)"
    if add:
        _obj, created = AssignedEmail.objects.get_or_create(client=client, email=email)
        if not client.is_active:
            client.is_active = True
            client.save(update_fields=["is_active"])
        if created:
            send_message(chat_id, f"✅ Asigné <b>{html.escape(email)}</b> a {label} y lo activé.")
            send_message(
                client.telegram_chat_id,
                f"✅ El admin te asignó <b>{html.escape(email)}</b>. "
                "Ya podés pedir /codigo, /viaje, /hogar, /clave o /tv.",
            )
        else:
            send_message(chat_id, f"{label} ya tenía <b>{html.escape(email)}</b> asignado.")
    else:
        deleted, _ = AssignedEmail.objects.filter(client=client, email=email).delete()
        if deleted:
            send_message(chat_id, f"🗑 Le quité <b>{html.escape(email)}</b> a {label}.")
        else:
            send_message(chat_id, f"{label} no tenía <b>{html.escape(email)}</b> asignado.")


def _notify_admin_new(client: CodeBotClient) -> None:
    admin = _admin_chat_id()
    if not admin:
        return
    uname = f"@{client.telegram_username}" if client.telegram_username else "(sin usuario)"
    send_message(
        admin,
        "🆕 Nuevo cliente en el bot de códigos:\n"
        f"• Nombre: {html.escape(client.display_name or '—')}\n"
        f"• Usuario: {html.escape(uname)}\n"
        f"• Chat ID: <code>{html.escape(str(client.telegram_chat_id))}</code>\n\n"
        "Actívalo y asignale correos desde el panel.",
    )


# ---------- Menú de comandos de Telegram ----------

# Comandos que ve el cliente en el botón azul "Menú" de Telegram.
_CLIENT_MENU = [
    {"command": "codigo", "description": "🔑 Código de inicio de sesión"},
    {"command": "enlacesesion", "description": "🔗 Inicio sin contraseña Netflix"},
    {"command": "viaje", "description": "✈️ Código de acceso temporal (viaje)"},
    {"command": "hogar", "description": "🏠 Link para actualizar Hogar"},
    {"command": "clave", "description": "🔒 Link para restablecer contraseña"},
    {"command": "tv", "description": "📺 Activar Netflix en tu TV"},
    {"command": "enlacetv", "description": "📨 Buscar enlace de activación TV"},
    {"command": "miscorreos", "description": "📋 Ver mis correos asignados"},
    {"command": "buscar", "description": "🔍 Buscar un correo asignado"},
    {"command": "cmds", "description": "❓ Ver los comandos"},
]

# El admin ve, además, los comandos de administración.
_ADMIN_MENU = _CLIENT_MENU + [
    {"command": "emojiid", "description": "Obtener ID de un emoji Premium"},
    {"command": "clientes", "description": "👥 Lista de clientes"},
    {"command": "activar", "description": "🔓 Activar acceso de un cliente"},
    {"command": "desactivar", "description": "⏸ Pausar acceso de un cliente"},
    {"command": "asignar", "description": "➕ Asignar correo a un cliente"},
    {"command": "quitar", "description": "➖ Quitar correo a un cliente"},
    {"command": "anuncio", "description": "📢 Enviar anuncio a todos"},
]


def configure_commands() -> None:
    """Registra el menú de comandos en Telegram (botón azul "Menú")."""
    _call("setMyCommands", commands=_CLIENT_MENU, scope={"type": "default"})
    admin = _admin_chat_id()
    if admin:
        try:
            _call(
                "setMyCommands",
                commands=_ADMIN_MENU,
                scope={"type": "chat", "chat_id": int(admin)},
            )
        except (TypeError, ValueError):
            logger.warning("TELEGRAM_CODES_ADMIN_CHAT_ID inválido: %r", admin)


# ---------- Polling ----------

def process_update(update: dict) -> None:
    if "callback_query" in update:
        _handle_callback(update)
    else:
        _handle_message(update)


def run_polling(poll_interval: float = 1.0) -> None:
    if not is_configured():
        raise RuntimeError("TELEGRAM_CODES_BOT_TOKEN no configurado")
    try:
        configure_commands()
    except Exception:
        logger.exception("No se pudo configurar el menú de comandos (sigo igual)")
    # Retomamos desde el último update procesado: si el contenedor se
    # reinicia, no reprocesamos pedidos viejos.
    try:
        offset = BotState.get_offset()
    except Exception:
        logger.exception("No pude leer el offset guardado; arranco de 0")
        offset = 0
    logger.info("Bot de códigos iniciado (long polling), offset=%s", offset)
    while True:
        try:
            data = _call(
                "getUpdates",
                offset=offset,
                timeout=25,
                allowed_updates=["message", "callback_query"],
            )
            updates = data.get("result", [])
            for upd in updates:
                offset = upd["update_id"] + 1
                try:
                    process_update(upd)
                except Exception:
                    logger.exception("Error procesando update (codes)")
            # Persistimos el avance una vez por lote (menos escrituras a la DB).
            if updates:
                try:
                    BotState.set_offset(offset)
                except Exception:
                    logger.exception("No pude guardar el offset del bot")
        except requests.RequestException:
            logger.warning("getUpdates (codes) falló, reintentando…")
        time.sleep(poll_interval)
