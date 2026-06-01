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
    if cmd in ("/ayuda", "/help", "/cmds", "/comandos"):
        _send_commands_help(client)
        return
    if cmd == "/miscorreos":
        _send_email_menu(client)
        return

    # Comandos de admin (solo para el chat del admin).
    if _is_admin(chat_id) and cmd in ("/clientes", "/asignar", "/quitar", "/anuncio"):
        _handle_admin_command(chat_id, cmd, rest)
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
    # El mensaje de "pedí activación" es solo para clientes, no para el admin.
    if not client.is_active and not admin:
        send_message(
            chat_id,
            "👋 <b>¡Bienvenido al Bot de Códigos de Jheliz Store!</b> ✨\n\n"
            "Acá vas a obtener al instante los códigos de tu cuenta de Netflix:\n"
            "🔑 inicio de sesión · ✈️ viaje · 🏠 Hogar · 🔒 contraseña\n\n"
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
            "👋 <b>Hola, admin.</b> Bienvenido al Bot de Códigos de Jheliz Store.\n\n"
            + _admin_help_text(),
            buttons=_email_buttons(emails) if emails else None,
        )
        return
    if not emails:
        send_message(
            chat_id,
            "✅ <b>Tu cuenta está activada</b>, pero todavía no tenés correos asignados.\n"
            "El admin te los va a asignar en breve. Te aviso cuando estén listos 📩",
        )
        return
    send_message(chat_id, _client_help_text(emails), buttons=_email_buttons(emails))


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
        buttons=_email_buttons(emails) if emails else None,
    )


def _client_help_text(emails: list[str]) -> str:
    ejemplo = emails[0] if emails else "tucorreo@gmail.com"
    lines = [
        "✨ <b>Bot de Códigos · Jheliz Store</b>",
        "",
        "Escribí el comando con tu correo al lado 👇",
        "",
        f"🔑 <code>/codigo {ejemplo}</code> — código de inicio de sesión",
        f"✈️ <code>/viaje {ejemplo}</code> — código de acceso temporal (de viaje)",
        f"🏠 <code>/hogar {ejemplo}</code> — link para actualizar Hogar",
        f"🔒 <code>/clave {ejemplo}</code> — link para restablecer contraseña",
        "",
        "📋 <code>/miscorreos</code> — ver tus correos asignados",
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
    else:
        lines.append("")
        lines.append("💡 También podés tocar un correo de abajo y elegir qué necesitás.")
    return "\n".join(lines)


def _admin_help_text() -> str:
    lines = [
        "🛠 <b>Panel de administrador · Jheliz Store</b>",
        "",
        "👥 <code>/clientes</code> — lista de clientes (ID, usuario, correos)",
        "➕ <code>/asignar &lt;ID o @usuario&gt; &lt;correo&gt;</code> — asigna y activa",
        "➖ <code>/quitar &lt;ID o @usuario&gt; &lt;correo&gt;</code> — quita un correo",
        "📢 <code>/anuncio &lt;mensaje&gt;</code> — enviar un anuncio a todos los registrados",
        "",
        "— También tenés los comandos de cliente —",
        "🔑 /codigo · ✈️ /viaje · 🏠 /hogar · 🔒 /clave · 📋 /miscorreos",
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
    body = "📢 <b>Anuncio · Jheliz Store</b>\n\n" + html.escape(message)
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
                "Ya podés pedir /codigo, /viaje, /hogar o /clave.",
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
    {"command": "viaje", "description": "✈️ Código de acceso temporal (viaje)"},
    {"command": "hogar", "description": "🏠 Link para actualizar Hogar"},
    {"command": "clave", "description": "🔒 Link para restablecer contraseña"},
    {"command": "miscorreos", "description": "📋 Ver mis correos asignados"},
    {"command": "cmds", "description": "❓ Ver los comandos"},
]

# El admin ve, además, los comandos de administración.
_ADMIN_MENU = _CLIENT_MENU + [
    {"command": "clientes", "description": "👥 Lista de clientes"},
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
