"""Utilidades para parsear y editar credenciales entregadas.

El ``delivered_credentials`` de un ``OrderItem`` es texto libre, pero en la
práctica tiene la forma::

    Correo: foo@bar.com
    Contraseña: secret123
    Perfil: Perfil 2
    PIN: 0000

Estas funciones permiten extraer email/contraseña para mostrar un preview
antes de un reemplazo masivo, y reescribir solo esas líneas dejando intactos
perfil/PIN y cualquier otro contenido libre.
"""

from __future__ import annotations

import re
from typing import NamedTuple


# Aliases que el admin suele usar para cada campo (case-insensitive).
_EMAIL_LABELS = ("correo", "email", "e-mail", "e mail", "usuario", "user")
_PASS_LABELS = ("contraseña", "contrasena", "password", "pass", "clave", "pw")
_PROFILE_LABELS = ("perfil", "profile")
_PIN_LABELS = ("pin", "código pin", "codigo pin")


def _line_re(labels: tuple[str, ...]) -> re.Pattern[str]:
    alt = "|".join(re.escape(x) for x in labels)
    # Captura la línea entera, con el label en group 1 y el valor en group 2.
    return re.compile(
        rf"^(?P<label>\s*(?:{alt}))\s*[:=]\s*(?P<value>.*?)\s*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )


_EMAIL_RE = _line_re(_EMAIL_LABELS)
_PASS_RE = _line_re(_PASS_LABELS)
_PROFILE_RE = _line_re(_PROFILE_LABELS)
_PIN_RE = _line_re(_PIN_LABELS)


def parse_profile_pin(text: str) -> tuple[str, str]:
    """Extrae perfil y PIN del texto de credenciales.

    Devuelve ``(perfil, pin)`` con strings vacíos si la línea no existe.
    Útil para mostrar columnas separadas en la lista de stock.
    """
    text = text or ""
    profile_match = _PROFILE_RE.search(text)
    pin_match = _PIN_RE.search(text)
    return (
        profile_match.group("value").strip() if profile_match else "",
        pin_match.group("value").strip() if pin_match else "",
    )


def split_account_extras(text: str) -> tuple[str, str, str]:
    """Separa el texto de credenciales en (cuenta, perfil, pin).

    ``cuenta`` mantiene todas las líneas que NO sean perfil/PIN para que
    pueda mostrarse aparte en una columna principal.
    """
    text = text or ""
    profile, pin = parse_profile_pin(text)
    rest_lines = []
    for line in text.splitlines():
        if _PROFILE_RE.match(line) or _PIN_RE.match(line):
            continue
        rest_lines.append(line)
    return "\n".join(rest_lines).rstrip(), profile, pin


class ParsedCredentials(NamedTuple):
    email: str
    password: str
    has_email_line: bool
    has_password_line: bool


def parse(text: str) -> ParsedCredentials:
    """Extrae email y contraseña del texto de credenciales.

    Si no hay una línea reconocible devuelve strings vacíos y marca los flags
    correspondientes como False (útil para mostrar advertencias en el
    preview).
    """
    text = text or ""
    email_match = _EMAIL_RE.search(text)
    pass_match = _PASS_RE.search(text)
    return ParsedCredentials(
        email=(email_match.group("value").strip() if email_match else ""),
        password=(pass_match.group("value").strip() if pass_match else ""),
        has_email_line=email_match is not None,
        has_password_line=pass_match is not None,
    )


def replace_account(text: str, new_email: str, new_password: str) -> str:
    """Devuelve el texto con la línea de email y de contraseña reemplazadas.

    - Si existe la línea original se mantiene el label que el admin escribió
      (``Correo:`` vs ``Email:``) para respetar el formato del admin.
    - Si no existía la línea, se agrega al inicio con los labels por defecto
      (``Correo:`` / ``Contraseña:``) para que el cliente tenga la info
      completa.
    - Perfil / PIN y cualquier otra línea se deja sin tocar.
    """
    text = text or ""
    new_email = (new_email or "").strip()
    new_password = (new_password or "").strip()

    def _sub_value(match: re.Match[str], value: str) -> str:
        label = match.group("label").rstrip()
        return f"{label}: {value}"

    parsed_email = _EMAIL_RE.search(text)
    if parsed_email is not None:
        text = _EMAIL_RE.sub(lambda m: _sub_value(m, new_email), text, count=1)
    else:
        text = f"Correo: {new_email}\n{text}".rstrip() + "\n"

    parsed_pass = _PASS_RE.search(text)
    if parsed_pass is not None:
        text = _PASS_RE.sub(lambda m: _sub_value(m, new_password), text, count=1)
    else:
        # Insertamos justo después de la línea de email si existe, sino al
        # principio para mantener la agrupación visual.
        lines = text.splitlines()
        inserted = False
        for i, line in enumerate(lines):
            if _EMAIL_RE.match(line):
                lines.insert(i + 1, f"Contraseña: {new_password}")
                inserted = True
                break
        if not inserted:
            lines.insert(0, f"Contraseña: {new_password}")
        text = "\n".join(lines).rstrip() + "\n"

    return text
