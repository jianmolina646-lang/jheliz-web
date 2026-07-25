"""Bot de Telegram y alertas de Jheliz Control sobre la base central."""

from __future__ import annotations

import hashlib
import html
import logging
import secrets
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from config.date_utils import add_service_duration

from .control_operations import (
    client_for_owner,
    clients_for_owner,
    create_client,
    create_subscription,
    delete_client,
    owner_finances,
    owner_summary,
    renew_subscription,
    search_clients,
    subscription_for_owner,
    subscriptions_for_owner,
    update_client,
)
from .models import Client, Service, Subscription, TelegramConnection, TelegramSession, Transaction

logger = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/{method}"
PAGE_SIZE = 5
WEB_URL = getattr(settings, "JHELIZ_CONTROL_BASE_URL", "https://jheliztv.xyz").rstrip("/")


def _call(method, **payload):
    token = settings.JHELIZ_CONTROL_TELEGRAM_BOT_TOKEN
    if not token:
        raise RuntimeError("JHELIZ_CONTROL_TELEGRAM_BOT_TOKEN no configurado")
    response = requests.post(API.format(token=token, method=method), json=payload, timeout=35)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "Telegram rechazó la solicitud"))
    return data


def _markup(rows):
    return {"inline_keyboard": rows}


def _button(text, callback_data=None, url=None):
    data = {"text": text}
    if callback_data:
        data["callback_data"] = callback_data
    if url:
        data["url"] = url
    return data


def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _call("sendMessage", **payload)


def _render(chat_id, text, reply_markup=None, message_id=None):
    if message_id:
        try:
            return _call(
                "editMessageText",
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup or _markup([]),
            )
        except Exception:
            logger.info("No se pudo editar el mensaje; se enviará uno nuevo", exc_info=True)
    return send_message(chat_id, text, reply_markup)


def _ack(callback_id, text=""):
    try:
        _call("answerCallbackQuery", callback_query_id=callback_id, text=text[:180])
    except Exception:
        logger.info("No se pudo confirmar callback Telegram", exc_info=True)


def _linked_connection(chat_id):
    connection = (
        TelegramConnection.objects.filter(chat_id=str(chat_id), is_enabled=True)
        .select_related("owner", "owner__jc_tenant")
        .first()
    )
    if not connection:
        return None
    return connection


def _has_active_access(connection):
    try:
        return connection.owner.jc_tenant.subscription_active
    except Exception:
        return False


def _inactive_plan(chat_id, message_id=None):
    return _render(
        chat_id,
        "⛔ <b>Suscripción de Jheliz Control vencida</b>\n\n"
        "Renueva tu plan para volver a gestionar clientes desde Telegram.",
        _markup([[_button("💳 Renovar en Jheliz Control", url=f"{WEB_URL}/suscripcion/")]]),
        message_id,
    )


def _session(connection):
    return TelegramSession.objects.get_or_create(connection=connection)[0]


def _reset_session(connection, message_id=None):
    session = _session(connection)
    session.state = ""
    session.data = {}
    if message_id:
        session.menu_message_id = message_id
    session.save()
    return session


def subscriptions_for_connection(connection):
    return subscriptions_for_owner(connection.owner_id)


@transaction.atomic
def link_chat(raw_token, chat):
    digest = hashlib.sha256(raw_token.encode()).hexdigest()
    connection = (
        TelegramConnection.objects.select_for_update()
        .filter(link_token_digest=digest, link_expires_at__gt=timezone.now())
        .first()
    )
    if not connection:
        return False
    TelegramConnection.objects.filter(chat_id=str(chat["id"])).exclude(pk=connection.pk).update(
        chat_id=None, is_enabled=False
    )
    connection.chat_id = str(chat["id"])
    connection.telegram_username = chat.get("username", "")
    connection.linked_at = timezone.now()
    connection.link_token_digest = ""
    connection.link_expires_at = None
    connection.is_enabled = True
    connection.save()
    TelegramSession.objects.filter(connection=connection).delete()
    return True


def _unlinked(chat_id, message_id=None):
    return _render(
        chat_id,
        "🔐 <b>Telegram no vinculado</b>\n\n"
        "Para usar Jheliz Control desde Telegram primero debes vincular tu cuenta.",
        _markup([[_button("🔗 Vincular Telegram", url=f"{WEB_URL}/app/telegram/")]]),
        message_id,
    )


def _main_menu(connection, message_id=None):
    summary = owner_summary(connection.owner_id)
    owner_name = html.escape(connection.owner.get_full_name() or connection.owner.username)
    text = (
        "🤖 <b>JHELIZ CONTROL</b>\n\n"
        f"Hola, <b>{owner_name}</b> 👋\n\n"
        "📊 <b>RESUMEN</b>\n"
        f"👥 Clientes: <b>{summary['clients']}</b>\n"
        f"🟢 Activas: <b>{summary['active']}</b>\n"
        f"⏰ Por vencer: <b>{summary['due']}</b>\n"
        f"🔴 Vencidas: <b>{summary['expired']}</b>"
    )
    keyboard = _markup(
        [
            [_button("👥 Mis clientes", "clients:0:all"), _button("➕ Nuevo cliente", "new")],
            [_button("⏰ Próximos vencimientos", "due:0"), _button("📊 Estadísticas", "stats")],
            [_button("💰 Mi saldo", "balance"), _button("🔔 Alertas", "alerts")],
            [_button("⚙️ Mi cuenta", "account"), _button("🌐 Abrir Jheliz Control", url=f"{WEB_URL}/app/")],
        ]
    )
    _reset_session(connection, message_id)
    return _render(connection.chat_id, text, keyboard, message_id)


def _status_for_client(client):
    now = timezone.now()
    soon = now + timedelta(days=3)
    subs = list(client.subscriptions.filter(is_archived=False).order_by("expires_at"))
    if not subs:
        return "Sin suscripciones", "⚪", None
    earliest = subs[0].expires_at
    if earliest <= now:
        return "Vencido", "🔴", earliest
    if earliest <= soon:
        return "Por vencer", "⏰", earliest
    return "Activo", "🟢", earliest


def _clients_menu(connection, page=0, status="all", query="", message_id=None):
    now = timezone.now()
    soon = now + timedelta(days=3)
    qs = search_clients(connection.owner_id, query)
    if status == "active":
        qs = qs.filter(subscriptions__is_archived=False, subscriptions__expires_at__gt=soon).distinct()
    elif status == "due":
        qs = qs.filter(
            subscriptions__is_archived=False,
            subscriptions__expires_at__gt=now,
            subscriptions__expires_at__lte=soon,
        ).distinct()
    elif status == "expired":
        qs = qs.filter(subscriptions__is_archived=False, subscriptions__expires_at__lte=now).distinct()
    total = qs.count()
    page = max(0, int(page))
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, pages - 1)
    clients = list(qs[(page * PAGE_SIZE):((page + 1) * PAGE_SIZE)])
    lines = ["👥 <b>MIS CLIENTES</b>", f"Página {page + 1} de {pages} · {total} resultado(s)"]
    rows = []
    for client in clients:
        label, icon, expires = _status_for_client(client)
        date = timezone.localtime(expires).strftime("%d/%m/%Y") if expires else "—"
        lines.append(f"\n{icon} <b>{html.escape(client.name)}</b>\n{label} · {date}")
        rows.append([_button(f"👁 {client.name[:30]}", f"client:{client.pk}")])
    if not clients:
        lines.append("\nNo encontramos clientes con este filtro.")
    nav = []
    if page > 0:
        nav.append(_button("⬅️ Anterior", f"clients:{page - 1}:{status}"))
    if page + 1 < pages:
        nav.append(_button("Siguiente ➡️", f"clients:{page + 1}:{status}"))
    if nav:
        rows.append(nav)
    rows.extend(
        [
            [_button("🔎 Buscar", "search"), _button("🟢 Activos", "clients:0:active")],
            [_button("⏰ Por vencer", "clients:0:due"), _button("🔴 Vencidos", "clients:0:expired")],
            [_button("⬅️ Volver", "menu")],
        ]
    )
    return _render(connection.chat_id, "\n".join(lines), _markup(rows), message_id)


def _client_detail(connection, client_id, message_id=None):
    client = client_for_owner(connection.owner_id, client_id)
    if not client:
        return _render(
            connection.chat_id,
            "⚠️ El cliente no existe o no tienes permiso para verlo.",
            _markup([[_button("⬅️ Volver", "clients:0:all")]]),
            message_id,
        )
    label, icon, _ = _status_for_client(client)
    lines = [
        "👤 <b>DETALLE DEL CLIENTE</b>",
        f"\n<b>Nombre:</b> {html.escape(client.name)}",
    ]
    for title, value in (
        ("WhatsApp", client.whatsapp),
        ("Correo", client.email),
        ("Telegram", client.telegram),
        ("Notas", client.notes),
    ):
        if value:
            lines.append(f"<b>{title}:</b> {html.escape(value)}")
    lines.append(f"\n<b>Estado:</b> {icon} {label}")
    rows = []
    subs = list(
        subscriptions_for_owner(connection.owner_id)
        .filter(client_id=client.pk)
        .select_related("service")
        .order_by("expires_at")
    )
    if subs:
        lines.append("\n📦 <b>Suscripciones</b>")
        for sub in subs[:8]:
            when = timezone.localtime(sub.expires_at).strftime("%d/%m/%Y")
            lines.append(
                f"• {html.escape(sub.service.name)} · {html.escape(sub.get_plan_display())} · {when}"
            )
            rows.append([_button(f"🔄 Renovar {sub.service.name[:22]}", f"renew_menu:{sub.pk}")])
    else:
        lines.append("\nNo tiene suscripciones registradas.")
    rows.extend(
        [
            [_button("➕ Agregar suscripción", f"subnew:{client.pk}")],
            [_button("✏️ Editar", f"edit_menu:{client.pk}"), _button("🗑 Eliminar", f"delete_ask:{client.pk}")],
            [_button("⬅️ Mis clientes", "clients:0:all"), _button("🏠 Menú", "menu")],
        ]
    )
    return _render(connection.chat_id, "\n".join(lines), _markup(rows), message_id)


def _new_start(connection, message_id=None):
    session = _session(connection)
    session.state = "new:name"
    session.data = {}
    session.save()
    return _render(
        connection.chat_id,
        "➕ <b>NUEVO CLIENTE</b>\n\nPaso 1 de 5\n👤 Ingresa el nombre del cliente.",
        _markup([[_button("❌ Cancelar", "menu")]]),
        message_id,
    )


def _new_text(connection, text):
    session = _session(connection)
    field = session.state.split(":", 1)[1]
    optional = field != "name"
    value = "" if optional and text.lower() in {"/omitir", "omitir", "-"} else text.strip()
    if field == "name" and not value:
        return send_message(connection.chat_id, "El nombre es obligatorio. Inténtalo nuevamente.")
    session.data[field] = value
    fields = ["name", "whatsapp", "email", "telegram", "notes"]
    index = fields.index(field)
    if index + 1 < len(fields):
        next_field = fields[index + 1]
        prompts = {
            "whatsapp": "📱 Ingresa el WhatsApp o escribe /omitir.",
            "email": "📧 Ingresa el correo o escribe /omitir.",
            "telegram": "✈️ Ingresa el usuario de Telegram o escribe /omitir.",
            "notes": "📝 Añade una nota o escribe /omitir.",
        }
        session.state = f"new:{next_field}"
        session.save()
        return send_message(
            connection.chat_id,
            f"Paso {index + 2} de 5\n{prompts[next_field]}",
            _markup([[_button("❌ Cancelar", "menu")]]),
        )
    nonce = secrets.token_hex(4)
    session.state = "new:confirm"
    session.data["nonce"] = nonce
    session.save()
    data = session.data
    preview = [
        "📋 <b>CONFIRMAR CLIENTE</b>",
        f"\n👤 Nombre: {html.escape(data['name'])}",
        f"📱 WhatsApp: {html.escape(data.get('whatsapp') or 'No indicado')}",
        f"📧 Correo: {html.escape(data.get('email') or 'No indicado')}",
        f"✈️ Telegram: {html.escape(data.get('telegram') or 'No indicado')}",
    ]
    return send_message(
        connection.chat_id,
        "\n".join(preview),
        _markup(
            [
                [_button("✅ Registrar cliente", f"new_confirm:{nonce}")],
                [_button("✏️ Volver a empezar", "new"), _button("❌ Cancelar", "menu")],
            ]
        ),
    )


def _subscription_new_start(connection, client_id, message_id=None):
    client = client_for_owner(connection.owner_id, client_id)
    if not client:
        return _clients_menu(connection, message_id=message_id)
    services = list(Service.objects.filter(owner_id=connection.owner_id, is_active=True).order_by("name"))
    if not services:
        return _render(
            connection.chat_id,
            "⚠️ Primero debes crear al menos un servicio desde Jheliz Control Web.",
            _markup(
                [
                    [_button("🌐 Abrir servicios", url=f"{WEB_URL}/app/servicios/")],
                    [_button("⬅️ Volver", f"client:{client.pk}")],
                ]
            ),
            message_id,
        )
    rows = [
        [_button(f"📦 {service.name[:32]}", f"subnew_service:{client.pk}:{service.pk}")]
        for service in services[:30]
    ]
    rows.append([_button("❌ Cancelar", f"client:{client.pk}")])
    return _render(
        connection.chat_id,
        f"➕ <b>NUEVA SUSCRIPCIÓN</b>\n\nCliente: <b>{html.escape(client.name)}</b>\n"
        "Selecciona el servicio:",
        _markup(rows),
        message_id,
    )


def _subscription_new_text(connection, text):
    session = _session(connection)
    field = session.state.split(":", 1)[1]
    value = "" if text.lower() in {"/omitir", "omitir", "-"} else text.strip()
    data = session.data
    if field == "account_email":
        if not value:
            return send_message(connection.chat_id, "El correo o usuario de la cuenta es obligatorio.")
        data["account_email"] = value
        session.state = "subnew:account_password"
        session.data = data
        session.save()
        return send_message(
            connection.chat_id,
            "🔐 Escribe la contraseña de la cuenta o usa /omitir.",
            _markup([[_button("❌ Cancelar", f"client:{data['client_id']}")]]),
        )
    if field == "account_password":
        data["account_password"] = value
        session.state = "subnew:plan"
        session.data = data
        session.save()
        return send_message(
            connection.chat_id,
            "📦 Selecciona la modalidad:",
            _markup(
                [
                    [_button("👤 Perfil", "subnew_plan:perfil"), _button("📦 Cuenta completa", "subnew_plan:completa")],
                    [_button("❌ Cancelar", f"client:{data['client_id']}")],
                ]
            ),
        )
    if field == "profiles":
        try:
            data["profiles"] = max(1, min(7, int(value)))
        except ValueError:
            return send_message(connection.chat_id, "Escribe un número de perfiles entre 1 y 7.")
        session.state = "subnew:duration_days"
        session.data = data
        session.save()
        return send_message(connection.chat_id, "📅 Escribe la duración en días, por ejemplo 30.")
    if field == "duration_days":
        try:
            data["duration_days"] = max(1, min(3660, int(value)))
        except ValueError:
            return send_message(connection.chat_id, "Escribe una duración válida entre 1 y 3660 días.")
        session.state = "subnew:cost"
        session.data = data
        session.save()
        return send_message(
            connection.chat_id,
            "💵 Escribe el precio de venta o usa /omitir.",
        )
    if field == "cost":
        try:
            data["cost"] = str(float(value)) if value else "0"
        except ValueError:
            return send_message(connection.chat_id, "Escribe un monto válido, por ejemplo 10.00.")
        session.state = "subnew:investment"
        session.data = data
        session.save()
        return send_message(
            connection.chat_id,
            "💳 Escribe el costo de inversión o usa /omitir.",
        )
    if field == "investment":
        try:
            data["investment"] = str(float(value)) if value else "0"
        except ValueError:
            return send_message(connection.chat_id, "Escribe un monto válido, por ejemplo 5.00.")
        nonce = secrets.token_hex(4)
        data["nonce"] = nonce
        session.state = "subnew:confirm"
        session.data = data
        session.save()
        client = client_for_owner(connection.owner_id, data["client_id"])
        service = Service.objects.filter(owner_id=connection.owner_id, pk=data["service_id"]).first()
        if not client or not service:
            _reset_session(connection)
            return send_message(connection.chat_id, "⚠️ El cliente o servicio ya no está disponible.")
        return send_message(
            connection.chat_id,
            "📋 <b>CONFIRMAR SUSCRIPCIÓN</b>\n\n"
            f"👤 Cliente: {html.escape(client.name)}\n"
            f"📦 Servicio: {html.escape(service.name)}\n"
            f"📧 Cuenta: {html.escape(data['account_email'])}\n"
            f"🧩 Modalidad: {html.escape(Subscription.Plan(data['plan']).label)}\n"
            f"📅 Duración: {data['duration_days']} días\n"
            f"💵 Venta: {html.escape(data['cost'])}\n"
            f"💳 Inversión: {html.escape(data['investment'])}",
            _markup(
                [
                    [_button("✅ Registrar suscripción", f"subnew_confirm:{nonce}")],
                    [_button("❌ Cancelar", f"client:{client.pk}")],
                ]
            ),
        )


def _edit_menu(connection, client_id, message_id=None):
    client = client_for_owner(connection.owner_id, client_id)
    if not client:
        return _client_detail(connection, client_id, message_id)
    return _render(
        connection.chat_id,
        f"✏️ <b>EDITAR CLIENTE</b>\n\nSelecciona el dato de <b>{html.escape(client.name)}</b> que deseas cambiar.",
        _markup(
            [
                [_button("👤 Nombre", f"edit:{client.pk}:name"), _button("📱 WhatsApp", f"edit:{client.pk}:whatsapp")],
                [_button("📧 Correo", f"edit:{client.pk}:email"), _button("✈️ Telegram", f"edit:{client.pk}:telegram")],
                [_button("📝 Notas", f"edit:{client.pk}:notes")],
                [_button("⬅️ Volver", f"client:{client.pk}")],
            ]
        ),
        message_id,
    )


def _renew_menu(connection, subscription_id, message_id=None):
    sub = subscription_for_owner(connection.owner_id, subscription_id)
    if not sub:
        return _render(
            connection.chat_id,
            "⚠️ La suscripción no existe o no tienes permiso.",
            _markup([[_button("🏠 Menú", "menu")]]),
            message_id,
        )
    current = timezone.localtime(sub.expires_at).strftime("%d/%m/%Y")
    return _render(
        connection.chat_id,
        "🔄 <b>RENOVAR SUSCRIPCIÓN</b>\n\n"
        f"👤 {html.escape(sub.client.name)}\n"
        f"📦 {html.escape(sub.service.name)}\n"
        f"📅 Vencimiento actual: <b>{current}</b>\n\n"
        "Selecciona la duración:",
        _markup(
            [
                [_button("30 días", f"renew_ask:{sub.pk}:30"), _button("60 días", f"renew_ask:{sub.pk}:60")],
                [_button("90 días", f"renew_ask:{sub.pk}:90"), _button("Personalizado", f"renew_custom:{sub.pk}")],
                [_button("⬅️ Volver", f"client:{sub.client_id}")],
            ]
        ),
        message_id,
    )


def _renew_confirm(connection, subscription_id, days, message_id=None):
    sub = subscription_for_owner(connection.owner_id, subscription_id)
    if not sub:
        return _renew_menu(connection, subscription_id, message_id)
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 30
    base = sub.expires_at if sub.expires_at > timezone.now() else timezone.now()
    new_date = timezone.localtime(add_service_duration(base, days)).strftime("%d/%m/%Y")
    nonce = secrets.token_hex(4)
    session = _session(connection)
    session.state = "renew:confirm"
    session.data = {"subscription_id": sub.pk, "days": days, "nonce": nonce}
    session.save()
    return _render(
        connection.chat_id,
        "📋 <b>CONFIRMAR RENOVACIÓN</b>\n\n"
        f"Cliente: <b>{html.escape(sub.client.name)}</b>\n"
        f"Servicio: {html.escape(sub.service.name)}\n"
        f"Nueva fecha: <b>{new_date}</b>",
        _markup(
            [
                [_button("✅ Confirmar renovación", f"renew_confirm:{nonce}")],
                [_button("❌ Cancelar", f"client:{sub.client_id}")],
            ]
        ),
        message_id,
    )


def _stats(connection, message_id=None):
    summary = owner_summary(connection.owner_id)
    now = timezone.now()
    month_new = clients_for_owner(connection.owner_id).filter(
        created_at__year=now.year, created_at__month=now.month
    ).count()
    text = (
        "📊 <b>ESTADÍSTICAS</b>\n\n"
        f"👥 Total de clientes: <b>{summary['clients']}</b>\n"
        f"🟢 Suscripciones activas: <b>{summary['active']}</b>\n"
        f"⏰ Por vencer: <b>{summary['due']}</b>\n"
        f"🔴 Vencidas: <b>{summary['expired']}</b>\n"
        f"🆕 Clientes nuevos este mes: <b>{month_new}</b>"
    )
    return _render(connection.chat_id, text, _markup([[_button("⬅️ Volver", "menu")]]), message_id)


def _balance(connection, message_id=None):
    values = owner_finances(connection.owner)
    currency = html.escape(values["currency"])
    text = (
        "💰 <b>MI SALDO</b>\n\n"
        f"Créditos disponibles: <b>{currency} {values['credits']}</b>\n"
        f"Ingresos registrados: <b>{currency} {values['income']}</b>\n"
        f"Egresos registrados: <b>{currency} {values['expense']}</b>\n"
        f"Balance: <b>{currency} {values['net']}</b>"
    )
    return _render(connection.chat_id, text, _markup([[_button("⬅️ Volver", "menu")]]), message_id)


def _alerts(connection, message_id=None):
    enabled = set(connection.windows())
    labels = [(7, "7 días"), (3, "3 días"), (1, "Mañana"), (0, "Hoy")]
    rows = [
        [_button(("✅ " if day in enabled else "❌ ") + label, f"alert_toggle:{day}")]
        for day, label in labels
    ]
    rows.append([_button("⬅️ Volver", "menu")])
    return _render(
        connection.chat_id,
        "🔔 <b>CONFIGURACIÓN DE ALERTAS</b>\n\n"
        "Activa o desactiva cuándo quieres recibir avisos de vencimiento.",
        _markup(rows),
        message_id,
    )


def _account(connection, message_id=None):
    linked = timezone.localtime(connection.linked_at).strftime("%d/%m/%Y %H:%M") if connection.linked_at else "—"
    return _render(
        connection.chat_id,
        "⚙️ <b>MI CUENTA</b>\n\n"
        f"👤 Revendedor: <b>{html.escape(connection.owner.username)}</b>\n"
        f"🆔 ID interno: <code>{connection.owner_id}</code>\n"
        "🔗 Telegram: <b>Vinculado</b>\n"
        f"📅 Vinculado desde: {linked}",
        _markup(
            [
                [_button("🔓 Desvincular Telegram", "unlink_ask")],
                [_button("🌐 Abrir panel", url=f"{WEB_URL}/app/"), _button("⬅️ Volver", "menu")],
            ]
        ),
        message_id,
    )


def _due(connection, message_id=None):
    today = timezone.localdate()
    rows = []
    lines = ["⏰ <b>PRÓXIMOS VENCIMIENTOS</b>"]
    labels = {0: "🔴 Hoy", 1: "🟠 Mañana", 3: "🟡 En 3 días", 7: "🟢 En 7 días"}
    found = 0
    for day in (0, 1, 3, 7):
        subs = (
            subscriptions_for_owner(connection.owner_id)
            .filter(expires_at__date=today + timedelta(days=day))
            .select_related("client", "service")
            .order_by("expires_at")
        )
        items = list(subs)
        if not items:
            continue
        lines.append(f"\n{labels[day]}")
        for sub in items[:10]:
            found += 1
            lines.append(f"• <b>{html.escape(sub.client.name)}</b> · {html.escape(sub.service.name)}")
            rows.append(
                [
                    _button("👁 Ver", f"client:{sub.client_id}"),
                    _button("🔄 Renovar", f"renew_menu:{sub.pk}"),
                ]
            )
    if not found:
        lines.append("\nNo hay vencimientos en estas fechas.")
    rows.append([_button("⬅️ Volver", "menu")])
    return _render(connection.chat_id, "\n".join(lines), _markup(rows), message_id)


def _handle_text_state(connection, text):
    session = _session(connection)
    if session.state.startswith("new:") and session.state != "new:confirm":
        return _new_text(connection, text)
    if session.state.startswith("subnew:") and session.state not in {"subnew:plan", "subnew:confirm"}:
        return _subscription_new_text(connection, text)
    if session.state == "search":
        session.state = ""
        session.save()
        return _clients_menu(connection, query=text)
    if session.state.startswith("edit:"):
        _, client_id, field = session.state.split(":")
        client = client_for_owner(connection.owner_id, client_id)
        if not client:
            _reset_session(connection)
            return send_message(connection.chat_id, "⚠️ El cliente ya no existe.")
        data = {
            "name": client.name,
            "whatsapp": client.whatsapp,
            "email": client.email,
            "telegram": client.telegram,
            "notes": client.notes,
        }
        data[field] = "" if text.lower() in {"/vaciar", "vaciar"} else text.strip()
        updated, error = update_client(
            connection.owner,
            client.pk,
            data,
            idempotency_key=f"edit:{connection.owner_id}:{session.data.get('nonce')}",
        )
        _reset_session(connection)
        if error:
            return send_message(connection.chat_id, "⚠️ No pudimos guardar ese dato. Revisa el formato.")
        return _client_detail(connection, updated.pk)
    if session.state.startswith("renew_custom:"):
        subscription_id = session.state.split(":")[1]
        try:
            days = int(text)
        except ValueError:
            return send_message(connection.chat_id, "Escribe una cantidad válida de días, por ejemplo: 45.")
        if days < 1 or days > 3660:
            return send_message(connection.chat_id, "La duración debe estar entre 1 y 3660 días.")
        return _renew_confirm(connection, subscription_id, days)
    return _main_menu(connection)


def _handle_callback(connection, callback):
    data = callback.get("data") or ""
    callback_id = callback.get("id")
    message = callback.get("message") or {}
    message_id = message.get("message_id")
    _ack(callback_id)

    if data == "menu":
        return _main_menu(connection, message_id)
    if data.startswith("clients:"):
        _, page, status = data.split(":", 2)
        return _clients_menu(connection, page, status, message_id=message_id)
    if data == "search":
        session = _session(connection)
        session.state = "search"
        session.data = {}
        session.save()
        return _render(
            connection.chat_id,
            "🔎 <b>BUSCAR CLIENTE</b>\n\nEscribe nombre, WhatsApp, correo, Telegram o usuario de cuenta.",
            _markup([[_button("❌ Cancelar", "clients:0:all")]]),
            message_id,
        )
    if data.startswith("client:"):
        return _client_detail(connection, data.split(":")[1], message_id)
    if data == "new":
        return _new_start(connection, message_id)
    if data.startswith("new_confirm:"):
        nonce = data.split(":", 1)[1]
        session = _session(connection)
        if session.state != "new:confirm" or session.data.get("nonce") != nonce:
            return _ack(callback_id, "Esta confirmación ya venció.")
        client, error = create_client(
            connection.owner,
            session.data,
            idempotency_key=f"new:{connection.owner_id}:{nonce}",
        )
        _reset_session(connection)
        if error == "duplicate":
            return _ack(callback_id, "El cliente ya fue registrado.")
        if error:
            return _render(
                connection.chat_id,
                "⚠️ No pudimos registrar el cliente. Revisa sus datos.",
                _markup([[_button("➕ Intentar nuevamente", "new"), _button("🏠 Menú", "menu")]]),
                message_id,
            )
        return _render(
            connection.chat_id,
            f"✅ <b>Cliente registrado correctamente</b>\n\n👤 {html.escape(client.name)}",
            _markup(
                [
                    [_button("👁 Ver cliente", f"client:{client.pk}"), _button("➕ Registrar otro", "new")],
                    [_button("🏠 Menú principal", "menu")],
                ]
            ),
            message_id,
        )
    if data.startswith("subnew:"):
        return _subscription_new_start(connection, data.split(":")[1], message_id)
    if data.startswith("subnew_service:"):
        _, client_id, service_id = data.split(":")
        client = client_for_owner(connection.owner_id, client_id)
        service = Service.objects.filter(owner_id=connection.owner_id, pk=service_id).first()
        if not client or not service:
            return _render(
                connection.chat_id,
                "⚠️ El cliente o servicio no está disponible.",
                _markup([[_button("🏠 Menú", "menu")]]),
                message_id,
            )
        session = _session(connection)
        session.state = "subnew:account_email"
        session.data = {"client_id": client.pk, "service_id": service.pk}
        session.save()
        return _render(
            connection.chat_id,
            "➕ <b>NUEVA SUSCRIPCIÓN</b>\n\n"
            f"👤 {html.escape(client.name)}\n📦 {html.escape(service.name)}\n\n"
            "📧 Escribe el correo o usuario de la cuenta.",
            _markup([[_button("❌ Cancelar", f"client:{client.pk}")]]),
            message_id,
        )
    if data.startswith("subnew_plan:"):
        plan = data.split(":", 1)[1]
        session = _session(connection)
        if session.state != "subnew:plan" or plan not in {
            Subscription.Plan.PERFIL,
            Subscription.Plan.COMPLETA,
        }:
            return _ack(callback_id, "Esta operación ya venció.")
        session.data["plan"] = plan
        if plan == Subscription.Plan.PERFIL:
            session.state = "subnew:profiles"
            session.save()
            return _render(
                connection.chat_id,
                "👤 Escribe la cantidad de perfiles entre 1 y 7.",
                _markup([[_button("❌ Cancelar", f"client:{session.data['client_id']}")]]),
                message_id,
            )
        session.data["profiles"] = 1
        session.state = "subnew:duration_days"
        session.save()
        return _render(
            connection.chat_id,
            "📅 Escribe la duración en días, por ejemplo 30.",
            _markup([[_button("❌ Cancelar", f"client:{session.data['client_id']}")]]),
            message_id,
        )
    if data.startswith("subnew_confirm:"):
        nonce = data.split(":", 1)[1]
        session = _session(connection)
        if session.state != "subnew:confirm" or session.data.get("nonce") != nonce:
            return _ack(callback_id, "Esta confirmación ya venció.")
        sub, error = create_subscription(
            connection.owner,
            session.data,
            idempotency_key=f"subnew:{connection.owner_id}:{nonce}",
        )
        _reset_session(connection)
        if error == "duplicate":
            return _ack(callback_id, "La suscripción ya fue registrada.")
        if error:
            return _render(
                connection.chat_id,
                "⚠️ No pudimos registrar la suscripción.",
                _markup([[_button("🏠 Menú", "menu")]]),
                message_id,
            )
        return _render(
            connection.chat_id,
            "✅ <b>Suscripción registrada correctamente</b>\n\n"
            f"👤 {html.escape(sub.client.name)}\n"
            f"📦 {html.escape(sub.service.name)}\n"
            f"📅 Vence: {timezone.localtime(sub.expires_at):%d/%m/%Y}",
            _markup([[_button("👁 Ver cliente", f"client:{sub.client_id}"), _button("🏠 Menú", "menu")]]),
            message_id,
        )
    if data.startswith("edit_menu:"):
        return _edit_menu(connection, data.split(":")[1], message_id)
    if data.startswith("edit:"):
        _, client_id, field = data.split(":", 2)
        client = client_for_owner(connection.owner_id, client_id)
        if not client or field not in {"name", "whatsapp", "email", "telegram", "notes"}:
            return _client_detail(connection, client_id, message_id)
        session = _session(connection)
        session.state = f"edit:{client.pk}:{field}"
        session.data = {"nonce": secrets.token_hex(4)}
        session.save()
        current = html.escape(getattr(client, field) or "vacío")
        return _render(
            connection.chat_id,
            f"✏️ <b>EDITAR {field.upper()}</b>\n\nValor actual:\n<code>{current}</code>\n\n"
            "Escribe el valor nuevo. Usa /vaciar para dejarlo vacío.",
            _markup([[_button("❌ Cancelar", f"client:{client.pk}")]]),
            message_id,
        )
    if data.startswith("delete_ask:"):
        client = client_for_owner(connection.owner_id, data.split(":")[1])
        if not client:
            return _clients_menu(connection, message_id=message_id)
        nonce = secrets.token_hex(4)
        session = _session(connection)
        session.state = "delete:confirm"
        session.data = {"client_id": client.pk, "nonce": nonce}
        session.save()
        return _render(
            connection.chat_id,
            "⚠️ <b>¿Seguro que deseas eliminar este cliente?</b>\n\n"
            f"👤 {html.escape(client.name)}\n\nEsta acción elimina también sus suscripciones.",
            _markup(
                [
                    [_button("🗑 Sí, eliminar", f"delete_confirm:{nonce}")],
                    [_button("❌ Cancelar", f"client:{client.pk}")],
                ]
            ),
            message_id,
        )
    if data.startswith("delete_confirm:"):
        nonce = data.split(":", 1)[1]
        session = _session(connection)
        if session.state != "delete:confirm" or session.data.get("nonce") != nonce:
            return _ack(callback_id, "Esta confirmación ya venció.")
        deleted, error = delete_client(
            connection.owner,
            session.data["client_id"],
            idempotency_key=f"delete:{connection.owner_id}:{nonce}",
        )
        _reset_session(connection)
        text = "✅ Cliente eliminado correctamente." if deleted else "⚠️ El cliente ya no existe."
        return _render(
            connection.chat_id,
            text,
            _markup([[_button("👥 Mis clientes", "clients:0:all"), _button("🏠 Menú", "menu")]]),
            message_id,
        )
    if data.startswith("renew_menu:"):
        return _renew_menu(connection, data.split(":")[1], message_id)
    if data.startswith("renew_ask:"):
        _, subscription_id, days = data.split(":")
        return _renew_confirm(connection, subscription_id, days, message_id)
    if data.startswith("renew_custom:"):
        subscription_id = data.split(":")[1]
        sub = subscription_for_owner(connection.owner_id, subscription_id)
        if not sub:
            return _renew_menu(connection, subscription_id, message_id)
        session = _session(connection)
        session.state = f"renew_custom:{sub.pk}"
        session.data = {}
        session.save()
        return _render(
            connection.chat_id,
            "📅 Escribe la cantidad personalizada de días.",
            _markup([[_button("❌ Cancelar", f"renew_menu:{sub.pk}")]]),
            message_id,
        )
    if data.startswith("renew_confirm:"):
        nonce = data.split(":", 1)[1]
        session = _session(connection)
        if session.state != "renew:confirm" or session.data.get("nonce") != nonce:
            return _ack(callback_id, "Esta confirmación ya venció.")
        sub, error = renew_subscription(
            connection.owner,
            session.data["subscription_id"],
            session.data["days"],
            idempotency_key=f"renew:{connection.owner_id}:{nonce}",
        )
        _reset_session(connection)
        if error == "duplicate":
            return _ack(callback_id, "La renovación ya fue procesada.")
        if error:
            return _render(
                connection.chat_id,
                "⚠️ No pudimos renovar la suscripción.",
                _markup([[_button("🏠 Menú", "menu")]]),
                message_id,
            )
        new_date = timezone.localtime(sub.expires_at).strftime("%d/%m/%Y")
        return _render(
            connection.chat_id,
            f"✅ <b>Renovación realizada correctamente</b>\n\n📅 Nuevo vencimiento: <b>{new_date}</b>",
            _markup([[_button("👁 Ver cliente", f"client:{sub.client_id}"), _button("🏠 Menú", "menu")]]),
            message_id,
        )
    if data == "due":
        return _due(connection, message_id)
    if data.startswith("due:"):
        return _due(connection, message_id)
    if data == "stats":
        return _stats(connection, message_id)
    if data == "balance":
        return _balance(connection, message_id)
    if data == "alerts":
        return _alerts(connection, message_id)
    if data.startswith("alert_toggle:"):
        day = int(data.split(":")[1])
        windows = set(connection.windows())
        windows.remove(day) if day in windows else windows.add(day)
        connection.notify_windows = sorted(windows, reverse=True) if windows else [-1]
        connection.save(update_fields=["notify_windows", "updated_at"])
        return _alerts(connection, message_id)
    if data == "account":
        return _account(connection, message_id)
    if data == "unlink_ask":
        return _render(
            connection.chat_id,
            "🔓 <b>¿Desvincular Telegram?</b>\n\nDejarás de recibir alertas y perderás acceso desde este chat.",
            _markup(
                [
                    [_button("✅ Sí, desvincular", "unlink_confirm")],
                    [_button("❌ Cancelar", "account")],
                ]
            ),
            message_id,
        )
    if data == "unlink_confirm":
        chat_id = connection.chat_id
        connection.chat_id = None
        connection.telegram_username = ""
        connection.is_enabled = False
        connection.last_digest_date = None
        connection.save()
        return _render(
            chat_id,
            "✅ Telegram fue desvinculado de Jheliz Control.",
            _markup([[_button("🌐 Abrir Jheliz Control", url=f"{WEB_URL}/app/telegram/")]]),
            message_id,
        )
    return _ack(callback_id, "Acción no disponible.")


def process_update(update):
    callback = update.get("callback_query")
    if callback:
        chat = (callback.get("message") or {}).get("chat") or {}
        if not chat.get("id"):
            return
        connection = _linked_connection(chat["id"])
        if not connection:
            _ack(callback.get("id"), "Telegram no está vinculado.")
            return _unlinked(chat["id"], (callback.get("message") or {}).get("message_id"))
        if not _has_active_access(connection):
            _ack(callback.get("id"), "Tu suscripción está vencida.")
            return _inactive_plan(chat["id"], (callback.get("message") or {}).get("message_id"))
        return _handle_callback(connection, callback)

    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    if not chat.get("id"):
        return
    if text.startswith("/start "):
        linked = link_chat(text.split(maxsplit=1)[1], chat)
        if linked:
            connection = _linked_connection(chat["id"])
            if connection:
                send_message(
                    chat["id"],
                    "✅ <b>Jheliz Control conectado</b>\n\n"
                    "Tu cuenta quedó vinculada de forma segura. Solo podrás gestionar tus propios clientes.",
                )
                if not _has_active_access(connection):
                    return _inactive_plan(chat["id"])
                return _main_menu(connection)
        return send_message(
            chat["id"],
            "⚠️ El enlace venció o ya fue utilizado. Genera uno nuevo desde Jheliz Control.",
        )

    connection = _linked_connection(chat["id"])
    if not connection:
        return _unlinked(chat["id"])
    if not _has_active_access(connection):
        return _inactive_plan(chat["id"])
    if text in {"/start", "/menu", "/cancelar"}:
        return _main_menu(connection)
    if text == "/estado":
        return send_message(
            chat["id"],
            "✅ <b>Conexión activa</b>\n\n"
            f"Revendedor: <b>{html.escape(connection.owner.username)}</b>\n"
            "Privacidad: solo puedes acceder a tus propios clientes.",
            _markup([[_button("🏠 Abrir menú", "menu")]]),
        )
    return _handle_text_state(connection, text)


def run_polling():
    offset = 0
    try:
        _call(
            "setMyCommands",
            commands=[
                {"command": "menu", "description": "Abrir el panel principal"},
                {"command": "estado", "description": "Comprobar la vinculación"},
                {"command": "cancelar", "description": "Cancelar la operación actual"},
            ],
        )
    except Exception:
        logger.exception("No se pudieron registrar los comandos del bot")
    while True:
        try:
            data = _call(
                "getUpdates",
                offset=offset,
                timeout=25,
                allowed_updates=["message", "callback_query"],
            )
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                process_update(update)
        except Exception:
            logger.exception("Polling de Jheliz Control Telegram falló")
            time.sleep(5)


def send_expiry_digests(today=None):
    today = today or timezone.localdate()
    sent = 0
    connections = (
        TelegramConnection.objects.filter(is_enabled=True)
        .exclude(chat_id=None)
        .select_related("owner")
    )
    for connection in connections:
        if connection.last_digest_date == today:
            continue
        groups = []
        total_due = 0
        for window in connection.windows():
            target = today + timedelta(days=window)
            subscriptions = (
                subscriptions_for_owner(connection.owner_id)
                .filter(expires_at__date=target)
                .select_related("client", "service")
                .order_by("expires_at")
            )
            items = [
                f"• <b>{html.escape(sub.client.name)}</b>\n"
                f"  {html.escape(sub.service.name)} · vence "
                f"{timezone.localtime(sub.expires_at):%d/%m/%Y}"
                for sub in subscriptions
            ]
            if items:
                total_due += len(items)
                heading = (
                    "🚨 <b>Vencen hoy</b>"
                    if window == 0
                    else f"⏳ <b>Vencen en {window} día{'s' if window != 1 else ''}</b>"
                )
                groups.append(heading + "\n" + "\n".join(items))
        new_clients = Client.objects.filter(
            owner_id=connection.owner_id,
            created_at__date=today,
        ).count()
        sales = (
            Transaction.objects.filter(
                owner_id=connection.owner_id,
                kind=Transaction.Kind.INCOME,
                occurred_at__date=today,
            ).aggregate(value=Sum("amount"))["value"]
            or 0
        )
        if not groups and not new_clients and not sales:
            continue
        try:
            currency = html.escape(owner_finances(connection.owner)["currency"])
            daily = (
                "📊 <b>Resumen diario</b>\n"
                f"🆕 Clientes nuevos: <b>{new_clients}</b>\n"
                f"💰 Ventas registradas: <b>{currency} {sales}</b>\n\n"
            )
            expiry_text = (
                "🔔 <b>Vencimientos</b>\n"
                f"{total_due} suscripción{'es' if total_due != 1 else ''} "
                f"requiere{'n' if total_due != 1 else ''} atención.\n\n"
                + "\n\n".join(groups)
                + "\n\n"
                if groups
                else ""
            )
            send_message(
                connection.chat_id,
                daily + expiry_text + "Revisa los detalles desde Jheliz Control.",
                _markup([[_button("🤖 Abrir bot", "menu"), _button("🌐 Abrir panel", url=f"{WEB_URL}/app/")]]),
            )
        except Exception:
            logger.exception("No se pudo enviar resumen al owner=%s", connection.owner_id)
            continue
        connection.last_digest_date = today
        connection.save(update_fields=["last_digest_date", "updated_at"])
        sent += 1
    return sent
