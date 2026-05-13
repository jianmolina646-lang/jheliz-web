"""Auto-creación de usuarios para checkouts de invitado.

Cuando un visitante anónimo completa el checkout (sin estar logueado),
creamos un ``User`` con ``role=cliente`` para que el comprador aparezca en
la sección "Zona de clientes" del admin. El usuario queda sin contraseña
utilizable, así que no puede iniciar sesión hasta reclamar la cuenta
(por ejemplo, vía reseteo de contraseña con el correo registrado).
"""
from __future__ import annotations

import logging
import re
import secrets

from django.contrib.auth import get_user_model

from .models import Role

logger = logging.getLogger(__name__)

User = get_user_model()

_USERNAME_INVALID_RE = re.compile(r"[^a-zA-Z0-9_.\-]")


def _username_from_email(email: str) -> str:
    """Construye un slug de username a partir del local-part de un email.

    Ejemplo: ``"John+Doe@gmail.com"`` -> ``"john.doe"``. Si el resultado
    queda vacío (caso raro), genera un fallback aleatorio.
    """
    local = email.split("@", 1)[0].lower()
    slug = _USERNAME_INVALID_RE.sub(".", local).strip(".")
    return slug or f"cliente_{secrets.token_hex(4)}"


def _unique_username(base: str) -> str:
    """Devuelve ``base`` si está libre; si no, prueba ``base.2``, ``base.3``…"""
    if not User.objects.filter(username=base).exists():
        return base
    for n in range(2, 1000):
        candidate = f"{base}.{n}"
        if not User.objects.filter(username=candidate).exists():
            return candidate
    return f"{base}.{secrets.token_hex(4)}"


def get_or_create_guest_user(
    *,
    email: str,
    full_name: str = "",
    phone: str = "",
    telegram_username: str = "",
):
    """Devuelve el ``User`` correspondiente a un comprador invitado.

    Si ya existe un User con ese email, lo retorna sin duplicar (y completa
    los datos de contacto vacíos: phone, telegram_username, first/last
    name). Si no existe, crea uno con ``role=cliente`` y contraseña
    inutilizable.
    """
    email = (email or "").strip()
    if not email:
        raise ValueError("email es requerido para crear un User invitado")

    existing = User.objects.filter(email__iexact=email).first()
    if existing is not None:
        updates: list[str] = []
        if phone and not existing.phone:
            existing.phone = phone[:30]
            updates.append("phone")
        if telegram_username and not existing.telegram_username:
            existing.telegram_username = telegram_username[:60]
            updates.append("telegram_username")
        if full_name and not (existing.first_name or existing.last_name):
            first, _, last = full_name.strip().partition(" ")
            existing.first_name = first[:150]
            existing.last_name = last[:150]
            updates.extend(["first_name", "last_name"])
        if updates:
            existing.save(update_fields=updates)
        return existing

    username = _unique_username(_username_from_email(email))
    first_name, _, last_name = (full_name or "").strip().partition(" ")

    user = User(
        username=username,
        email=email,
        first_name=first_name[:150],
        last_name=last_name[:150],
        phone=phone[:30] if phone else "",
        telegram_username=telegram_username[:60] if telegram_username else "",
        role=Role.CLIENTE,
    )
    user.set_unusable_password()
    user.save()
    logger.info(
        "Auto-creado User invitado id=%s username=%s email=%s",
        user.id, user.username, email,
    )
    return user
