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
import time
from typing import Any, Iterable

import requests
from django.conf import settings

from . import imap_reader
from .models import AssignedEmail, CodeBotClient

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


# ---------- Configuración ----------

def _token() -> str:
    return getattr(settings, "TELEGRAM_CODES_BOT_TOKEN", "") or ""


def _admin_chat_id() -> str:
    return str(getattr(settings, "TELEGRAM_CODES_ADMIN_CHAT_ID", "") or "")


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


def send_message(
    chat_id: str | int,
    text: str,
    buttons: Iterable[Iterable[dict]] | None = None,
) -> dict:
    payload: dict[str, Any] = {
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    markup = _build_reply_markup(buttons)
    if markup:
        payload["reply_markup"] = markup
    return _call("sendMessage", **payload)


def answer_callback_query(callback_query_id: str, text: str = "") -> dict:
    payload: dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    return _call("answerCallbackQuery", **payload)


# ---------- Helpers de dominio ----------

def _get_or_create_client(chat_id: str, username: str, name: str) -> tuple[CodeBotClient, bool]:
    client, created = CodeBotClient.objects.get_or_create(
        telegram_chat_id=str(chat_id),
        defaults={"telegram_username": username or "", "display_name": name or ""},
    )
    # Mantené el username/nombre actualizados.
    changed = False
    if username and client.telegram_username != username:
        client.telegram_username = username
        changed = True
    if name and not client.display_name:
        client.display_name = name
        changed = True
    if changed:
        client.save(update_fields=["telegram_username", "display_name"])
    return client, created


def _assigned_emails(client: CodeBotClient) -> list[str]:
    return list(client.emails.values_list("email", flat=True))


def _email_buttons(emails: list[str]) -> list[list[dict]]:
    return [[{"text": e, "callback_data": f"code:{e}"}] for e in emails]


def _format_result(email: str, result) -> str:
    head = f"📧 <b>{html.escape(email)}</b>\n{html.escape(result.human_kind)}"
    parts = [head]
    if result.code:
        parts.append(f"\n🔢 Código: <code>{html.escape(result.code)}</code>")
    if result.action_url:
        parts.append(
            f'\n🔗 <a href="{html.escape(result.action_url)}">Abrir en Netflix</a>'
        )
    parts.append("\n\n⏱ Suele vencer en ~15 min. Si no funciona, generá uno nuevo y volvé a pedirlo.")
    return "".join(parts)


def _deliver_code(client: CodeBotClient, email: str) -> str:
    email = (email or "").strip().lower()
    assigned = set(_assigned_emails(client))
    if email not in assigned:
        return "Ese correo no está asignado a tu cuenta. Escribile al admin."
    if not imap_reader.is_configured():
        return "El servicio de códigos todavía no está configurado. Probá más tarde."
    try:
        result = imap_reader.fetch_latest_for_email(email)
    except Exception:
        logger.exception("Fallo leyendo IMAP para %s", email)
        return "Hubo un problema leyendo el correo. Probá de nuevo en un minuto."
    if result is None or not result.has_payload:
        return (
            f"No encontré un código reciente para <b>{html.escape(email)}</b>.\n"
            "Generá el código desde Netflix (reenviá el correo) y volvé a pedirlo."
        )
    client.touch()
    return _format_result(email, result)


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

    if text.startswith("/start"):
        if created:
            _notify_admin_new(client)
        _send_welcome(client)
        return
    if text.startswith("/ayuda") or text.startswith("/help"):
        _send_welcome(client)
        return
    if text.startswith("/miscorreos"):
        _send_email_menu(client)
        return

    # ¿Escribió un correo?
    if "@" in text and " " not in text:
        send_message(chat_id, _deliver_code(client, text))
        return

    _send_welcome(client)


def _handle_callback(update: dict) -> None:
    cq = update.get("callback_query") or {}
    data = cq.get("data") or ""
    cq_id = cq.get("id")
    chat = (cq.get("message") or {}).get("chat") or {}
    chat_id = chat.get("id")
    from_user = cq.get("from") or {}
    if chat_id is None:
        return
    client, _ = _get_or_create_client(
        chat_id, from_user.get("username") or "", from_user.get("first_name") or ""
    )
    if cq_id:
        answer_callback_query(cq_id, "Buscando…")
    if data.startswith("code:"):
        email = data.split(":", 1)[1]
        send_message(chat_id, _deliver_code(client, email))


def _send_welcome(client: CodeBotClient) -> None:
    chat_id = client.telegram_chat_id
    if not client.is_active:
        send_message(
            chat_id,
            "👋 ¡Hola! Tu acceso al bot de códigos todavía no está activado.\n\n"
            f"Tu ID es <code>{html.escape(str(chat_id))}</code>. "
            "Pasáselo al admin para que te active y te asigne tus correos.",
        )
        return
    emails = _assigned_emails(client)
    if not emails:
        send_message(
            chat_id,
            "Tu cuenta está activa pero todavía no tenés correos asignados.\n"
            "El admin te los va a asignar en breve.",
        )
        return
    send_message(
        chat_id,
        "✅ Elegí el correo del que querés el código de Netflix\n"
        "(o escribilo directamente):",
        buttons=_email_buttons(emails),
    )


def _send_email_menu(client: CodeBotClient) -> None:
    emails = _assigned_emails(client)
    if not client.is_active or not emails:
        _send_welcome(client)
        return
    send_message(
        client.telegram_chat_id,
        "Tus correos asignados:",
        buttons=_email_buttons(emails),
    )


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


# ---------- Polling ----------

def process_update(update: dict) -> None:
    if "callback_query" in update:
        _handle_callback(update)
    else:
        _handle_message(update)


def run_polling(poll_interval: float = 1.0) -> None:
    if not is_configured():
        raise RuntimeError("TELEGRAM_CODES_BOT_TOKEN no configurado")
    offset = 0
    logger.info("Bot de códigos iniciado (long polling)")
    while True:
        try:
            data = _call(
                "getUpdates",
                offset=offset,
                timeout=25,
                allowed_updates=["message", "callback_query"],
            )
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                try:
                    process_update(upd)
                except Exception:
                    logger.exception("Error procesando update (codes)")
        except requests.RequestException:
            logger.warning("getUpdates (codes) falló, reintentando…")
        time.sleep(poll_interval)
