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

# Los 4 comandos del cliente -> tipo de correo de Netflix que entregan.
# Telegram no permite tildes ni mayúsculas en los comandos, así que el
# comando real es sin tilde (/codigo, /clave) pero el cliente lo escribe igual.
COMMAND_KINDS: dict[str, str] = {
    "/codigo": "signin_code",
    "/viaje": "temp_code",
    "/hogar": "household",
    "/clave": "password_reset",
}

# Etiqueta corta de cada tipo, para botones y mensajes.
KIND_LABELS: dict[str, str] = {
    "signin_code": "🔑 Código de inicio de sesión",
    "temp_code": "✈️ Código de acceso temporal (viaje)",
    "household": "🏠 Actualizar Hogar",
    "password_reset": "🔒 Restablecer contraseña",
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


def _assigned_emails(client: CodeBotClient) -> list[str]:
    return list(client.emails.values_list("email", flat=True))


def _email_buttons(emails: list[str], kind: str | None = None) -> list[list[dict]]:
    """Botones para elegir un correo.

    El ``callback_data`` usa el índice del correo (no el correo entero) para
    no pasarse del límite de 64 bytes de Telegram. Si se pasa ``kind``, al
    tocar el botón se entrega ese tipo directamente; si no, se muestra el
    selector de tipo (``pick:<idx>``).
    """
    rows: list[list[dict]] = []
    for idx, e in enumerate(emails):
        data = f"c:{kind}:{idx}" if kind else f"pick:{idx}"
        rows.append([{"text": e, "callback_data": data}])
    return rows


def _kind_buttons(idx: int) -> list[list[dict]]:
    """Las 4 opciones de tipo para un correo (por índice)."""
    return [
        [{"text": KIND_LABELS[kind], "callback_data": f"c:{kind}:{idx}"}]
        for kind in COMMAND_KINDS.values()
    ]


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


def _deliver_code(client: CodeBotClient, email: str, kind: str | None = None) -> str:
    email = (email or "").strip().lower()
    assigned = set(_assigned_emails(client))
    if email not in assigned:
        return (
            f"⚠️ El correo <b>{html.escape(email)}</b> no está asignado a tu "
            "cuenta, así que no te corresponde. Si creés que es un error, "
            "escribile al admin."
        )
    if not imap_reader.is_configured():
        return "El servicio de códigos todavía no está configurado. Probá más tarde."
    try:
        result = imap_reader.fetch_latest_for_email(email, kind=kind)
    except Exception:
        logger.exception("Fallo leyendo IMAP para %s", email)
        return "Hubo un problema leyendo el correo. Probá de nuevo en un minuto."
    if result is None or not result.has_payload:
        if kind and kind in KIND_LABELS:
            que = f"<b>{html.escape(KIND_LABELS[kind])}</b>"
        else:
            que = "un código reciente"
        return (
            f"No encontré {que} para <b>{html.escape(email)}</b>.\n"
            "Generá el correo desde Netflix y volvé a pedirlo en un minuto."
        )
    client.touch()
    return _format_result(email, result)


def _cmd_code(client: CodeBotClient, kind: str, arg: str) -> None:
    """Procesa /codigo /viaje /hogar /clave [correo]."""
    chat_id = client.telegram_chat_id
    if not client.is_active:
        _send_welcome(client)
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
            send_message(
                chat_id,
                f"¿De qué correo querés <b>{html.escape(KIND_LABELS[kind])}</b>?\n"
                "Elegí uno (o repetí el comando con el correo al lado):",
                buttons=_email_buttons(emails, kind=kind),
            )
            return

    send_message(chat_id, _deliver_code(client, arg, kind=kind))


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

    cmd, _, rest = text.partition(" ")
    cmd = cmd.lower().split("@", 1)[0]  # quita @botname si lo hubiera
    rest = rest.strip()

    if cmd == "/start":
        if created:
            _notify_admin_new(client)
        _send_welcome(client)
        return
    if cmd in ("/ayuda", "/help"):
        _send_welcome(client)
        return
    if cmd == "/miscorreos":
        _send_email_menu(client)
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
    chat = (cq.get("message") or {}).get("chat") or {}
    chat_id = chat.get("id")
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
        if 0 <= idx < len(emails):
            send_message(chat_id, _deliver_code(client, emails[idx], kind=kind))
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
            send_message(
                chat_id,
                f"📧 <b>{html.escape(emails[idx])}</b>\n¿Qué necesitás?",
                buttons=_kind_buttons(idx),
            )
        return
    if cq_id:
        answer_callback_query(cq_id)


def _send_welcome(client: CodeBotClient) -> None:
    chat_id = client.telegram_chat_id
    admin = _is_admin(chat_id)
    # El mensaje de "pasáselo al admin" es solo para clientes, no para el admin.
    if not client.is_active and not admin:
        send_message(
            chat_id,
            "👋 ¡Hola! Tu acceso al bot de códigos todavía no está activado.\n\n"
            f"Tu ID es <code>{html.escape(str(chat_id))}</code>. "
            "Pasáselo al admin para que te active y te asigne tus correos.",
        )
        return
    emails = _assigned_emails(client)
    if not emails:
        if admin:
            send_message(
                chat_id,
                "👋 Hola admin. Acá ves los códigos de las cuentas que te "
                "asignes a vos mismo.\n\n"
                "Asigná correos a tus clientes desde el panel: "
                "<b>Bot de códigos → Clientes de código</b>, activá al cliente "
                "y agregale sus correos en la tabla de abajo.",
            )
            return
        send_message(
            chat_id,
            "Tu cuenta está activa pero todavía no tenés correos asignados.\n"
            "El admin te los va a asignar en breve.",
        )
        return
    send_message(chat_id, _help_text(emails), buttons=_email_buttons(emails))


def _help_text(emails: list[str]) -> str:
    ejemplo = emails[0] if emails else "correo@gmail.com"
    lines = [
        "👋 Bot de <b>códigos Jheliz</b>. Pedí lo que necesités con el correo al lado:",
        "",
        f"🔑 <code>/codigo {ejemplo}</code> — código de inicio de sesión",
        f"✈️ <code>/viaje {ejemplo}</code> — código de acceso temporal (de viaje)",
        f"🏠 <code>/hogar {ejemplo}</code> — link para actualizar Hogar",
        f"🔒 <code>/clave {ejemplo}</code> — link para restablecer contraseña",
    ]
    if len(emails) == 1:
        lines.append(
            "\nComo tenés un solo correo, también podés mandar el comando solo "
            "(ej. <code>/codigo</code>) y te lo doy de esa cuenta."
        )
    else:
        lines.append(
            "\nTambién podés tocar un correo de abajo y elegir qué necesitás."
        )
    lines.append("/miscorreos — ver tus correos asignados")
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
        f"📧 <b>{html.escape(email)}</b>\n¿Qué necesitás?",
        buttons=_kind_buttons(idx),
    )


def _send_email_menu(client: CodeBotClient) -> None:
    emails = _assigned_emails(client)
    if not client.is_active or not emails:
        _send_welcome(client)
        return
    send_message(
        client.telegram_chat_id,
        "Tus correos asignados. Tocá uno y elegí qué necesitás:",
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
