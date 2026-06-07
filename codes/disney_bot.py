"""Bot de Telegram de códigos de Disney+ (long polling).

Igual que el bot de Netflix pero dedicado a Disney+ y con **un solo**
comando: el cliente pide el **código de inicio de sesión** de las cuentas que
el admin le asignó.

- ``/start``: registra al cliente (queda pendiente) y le muestra su chat id.
- ``/codigo [correo]``: entrega el último código de inicio de sesión de Disney+.
  Con un solo correo asignado puede mandar ``/codigo`` a secas.
- Comandos de admin (solo el chat del admin): ``/clientes``, ``/asignar``,
  ``/quitar``.

Comparte el padrón de clientes (``CodeBotClient``/``AssignedEmail``) y la
casilla central (IMAP) con el bot de Netflix. Usa su propio token
(``TELEGRAM_DISNEY_BOT_TOKEN``), separado del bot de Netflix.
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
from .models import AssignedEmail, BotState, CodeBotClient

# Fila de offset propia del bot de Disney+ (Netflix usa pk=1).
BOT_STATE_PK = 2

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

# Único tipo que entrega el bot de Disney.
SIGNIN_KIND = "signin_code"
SERVICE = "disney"

# Validación simple de correo (suficiente para el panel del bot).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------- Configuración ----------

def _token() -> str:
    return getattr(settings, "TELEGRAM_DISNEY_BOT_TOKEN", "") or ""


def _admin_chat_id() -> str:
    # Por defecto, el mismo admin que el bot de Netflix.
    admin = getattr(settings, "TELEGRAM_DISNEY_ADMIN_CHAT_ID", "") or getattr(
        settings, "TELEGRAM_CODES_ADMIN_CHAT_ID", ""
    )
    return str(admin or "")


def _is_admin(chat_id) -> bool:
    admin = _admin_chat_id()
    return bool(admin) and str(chat_id) == admin


def is_configured() -> bool:
    return bool(_token())


# ---------- API low-level ----------

def _call(method: str, **payload) -> dict:
    token = _token()
    if not token:
        raise RuntimeError("TELEGRAM_DISNEY_BOT_TOKEN no configurado")
    url = TELEGRAM_API.format(token=token, method=method)
    resp = requests.post(url, json=payload, timeout=30)
    try:
        data = resp.json()
    except ValueError:
        data = {"ok": False, "description": resp.text}
    if not data.get("ok"):
        logger.warning("Telegram(disney) %s falló: %s", method, data)
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


def _email_buttons(emails: list[str]) -> list[list[dict]]:
    """Botones para elegir un correo (callback ``c:<idx>``).

    Usa el índice (no el correo) para no pasarse del límite de 64 bytes.
    """
    return [
        [{"text": e, "callback_data": f"c:{idx}"}] for idx, e in enumerate(emails)
    ]


def _format_result(email: str, result) -> str:
    parts = [f"📧 <b>{html.escape(email)}</b>\n🔑 Código de inicio de sesión de Disney+"]
    if result.code:
        parts.append(f"\n🔢 Código: <code>{html.escape(result.code)}</code>")
    if result.action_url:
        parts.append(
            f'\n🔗 <a href="{html.escape(result.action_url)}">Abrir en Disney+</a>'
        )
    parts.append(
        "\n\n⏱ Suele vencer en pocos minutos. Si no funciona, generá uno nuevo "
        "y volvé a pedirlo."
    )
    return "".join(parts)


def _deliver_code(client: CodeBotClient, email: str) -> str:
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
        result = imap_reader.fetch_latest_for_email(
            email, kind=SIGNIN_KIND, service=SERVICE
        )
    except Exception:
        logger.exception("Fallo leyendo IMAP (disney) para %s", email)
        return "Hubo un problema leyendo el correo. Probá de nuevo en un minuto."
    if result is None or not result.has_payload:
        return (
            f"No encontré un <b>código de inicio de sesión</b> de Disney+ para "
            f"<b>{html.escape(email)}</b>.\n"
            "Generá el correo desde Disney+ y volvé a pedirlo en un minuto."
        )
    client.touch()
    return _format_result(email, result)


def _cmd_code(client: CodeBotClient, arg: str) -> None:
    """Procesa /codigo [correo]."""
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
        if len(emails) == 1:
            arg = emails[0]
        else:
            send_message(
                chat_id,
                "¿De qué correo querés el <b>código de inicio de sesión</b>?\n"
                "Elegí uno (o repetí <code>/codigo</code> con el correo al lado):",
                buttons=_email_buttons(emails),
            )
            return

    send_message(chat_id, _deliver_code(client, arg))


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
    if cmd in ("/ayuda", "/help", "/miscorreos"):
        _send_welcome(client)
        return

    # Comandos de admin (solo para el chat del admin).
    if _is_admin(chat_id) and cmd in (
        "/clientes", "/asignar", "/quitar", "/anuncio", "/activar", "/desactivar"
    ):
        _handle_admin_command(chat_id, cmd, rest)
        return

    # Único comando de cliente.
    if cmd == "/codigo":
        _cmd_code(client, rest)
        return

    # ¿Escribió un correo a secas? Le damos el código directo.
    if "@" in text and " " not in text:
        if not client.is_active:
            _send_welcome(client)
            return
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
    emails = _assigned_emails(client)
    if data.startswith("c:"):
        # c:<idx> -> entregar el código del correo elegido.
        if cq_id:
            answer_callback_query(cq_id, "Buscando…")
        try:
            idx = int(data.split(":", 1)[1])
        except ValueError:
            return
        if 0 <= idx < len(emails):
            send_message(chat_id, _deliver_code(client, emails[idx]))
        return
    if cq_id:
        answer_callback_query(cq_id)


def _send_welcome(client: CodeBotClient) -> None:
    chat_id = client.telegram_chat_id
    admin = _is_admin(chat_id)
    if not client.is_active and not admin:
        send_message(
            chat_id,
            "👋 ¡Hola! Tu acceso al bot de códigos de Disney+ todavía no está "
            "activado.\n\n"
            f"Tu ID es <code>{html.escape(str(chat_id))}</code>. "
            "Pasáselo al admin para que te active y te asigne tus correos.",
        )
        return
    emails = _assigned_emails(client)
    if not emails:
        if admin:
            send_message(
                chat_id,
                "👋 Hola admin. Este es el bot de <b>Disney+</b> (solo código de "
                "inicio de sesión).\n\n"
                "🔧 <b>Comandos de admin</b> (asignás sin tocar la web):\n"
                "<code>/clientes</code> — lista tus clientes (ID, usuario, correos)\n"
                "<code>/activar &lt;ID o @usuario&gt;</code> — activa el acceso (sin asignar correo)\n"
                "<code>/desactivar &lt;ID o @usuario&gt;</code> — pausa el acceso\n"
                "<code>/asignar &lt;ID o @usuario&gt; &lt;correo&gt;</code> — asigna y activa\n"
                "<code>/quitar &lt;ID o @usuario&gt; &lt;correo&gt;</code> — quita un correo\n"
                "<code>/anuncio &lt;mensaje&gt;</code> — avisa a todos tus clientes\n\n"
                "El cliente tiene que mandar <b>/start</b> una vez para aparecer "
                "en <code>/clientes</code>. También podés asignar desde el panel web.",
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
        "👋 Bot de <b>códigos Disney+</b>. Pedí el código de inicio de sesión:",
        "",
        f"🔑 <code>/codigo {ejemplo}</code> — código de inicio de sesión",
    ]
    if len(emails) == 1:
        lines.append(
            "\nComo tenés un solo correo, también podés mandar <code>/codigo</code> "
            "a secas y te lo doy de esa cuenta."
        )
    else:
        lines.append("\nTambién podés tocar un correo de abajo.")
    return "\n".join(lines)


# ---------- Comandos de admin ----------

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
    """Activa o desactiva a un cliente sin tocar sus correos."""
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
            "✅ <b>El admin activó tu acceso al bot de Disney+.</b>\n"
            "En breve te asigna tus correos y vas a poder pedir <code>/codigo</code>.",
        )
    else:
        send_message(chat_id, f"⏸ Desactivé a {label}. Ya no puede pedir códigos hasta que lo reactives.")


def _admin_broadcast(chat_id, message: str) -> None:
    """Envía un anuncio a todos los que alguna vez hicieron /start."""
    message = (message or "").strip()
    if not message:
        send_message(
            chat_id,
            "Uso: <code>/anuncio &lt;mensaje&gt;</code>\n"
            "Ej: <code>/anuncio Mañana renuevo las cuentas, aviso cuando esté listo.</code>",
        )
        return
    body = "📢 <b>Anuncio · Disney+ Jheliz</b>\n\n" + html.escape(message)
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
            logger.exception("Anuncio (disney): fallo enviando a %s", rid)
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
                "Ya podés pedir <code>/codigo</code>.",
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
        "🆕 Nuevo cliente en el bot de Disney+:\n"
        f"• Nombre: {html.escape(client.display_name or '—')}\n"
        f"• Usuario: {html.escape(uname)}\n"
        f"• Chat ID: <code>{html.escape(str(client.telegram_chat_id))}</code>\n\n"
        "Actívalo y asignale correos desde el panel o con <code>/asignar</code>.",
    )


# ---------- Menú de comandos de Telegram ----------

# Comandos que ve el cliente en el botón azul "Menú" de Telegram.
_CLIENT_MENU = [
    {"command": "codigo", "description": "🔑 Código de inicio de sesión"},
]

# El admin ve, además, los comandos de administración.
_ADMIN_MENU = _CLIENT_MENU + [
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
            logger.warning("TELEGRAM_DISNEY_ADMIN_CHAT_ID inválido: %r", admin)


# ---------- Polling ----------

def process_update(update: dict) -> None:
    if "callback_query" in update:
        _handle_callback(update)
    else:
        _handle_message(update)


def run_polling(poll_interval: float = 1.0) -> None:
    if not is_configured():
        raise RuntimeError("TELEGRAM_DISNEY_BOT_TOKEN no configurado")
    try:
        configure_commands()
    except Exception:
        logger.exception("No se pudo configurar el menú de comandos (sigo igual)")
    try:
        offset = BotState.get_offset(pk=BOT_STATE_PK)
    except Exception:
        logger.exception("No pude leer el offset guardado; arranco de 0")
        offset = 0
    logger.info("Bot de Disney+ iniciado (long polling), offset=%s", offset)
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
                    logger.exception("Error procesando update (disney)")
            if updates:
                try:
                    BotState.set_offset(offset, pk=BOT_STATE_PK)
                except Exception:
                    logger.exception("No pude guardar el offset del bot (disney)")
        except requests.RequestException:
            logger.warning("getUpdates (disney) falló, reintentando…")
        time.sleep(poll_interval)
