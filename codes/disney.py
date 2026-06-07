"""Parser de los correos de Disney+.

Para el bot de Disney solo nos interesa **un** tipo de correo: el del
**código de inicio de sesión** (one-time passcode / código de acceso único)
que Disney+ envía cuando alguien quiere entrar a la cuenta.

- **signin_code**: "Tu código de acceso", "código de un solo uso",
  "one-time passcode", "verification code"… Trae un número (normalmente de
  6 dígitos) que es el que el cliente necesita.
- **other**: cualquier otro correo de Disney+ (novedades, recibos, etc.) que
  no entregamos.

NOTA: los formatos exactos de Disney+ cambian y varían por idioma. El
clasificador se basa en palabras clave del asunto/cuerpo y la extracción del
código es best-effort; está pensado para refinarse con muestras reales.
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field

# Palabras clave que identifican el correo de código de inicio de sesión.
# Se cubren variantes en español (LatAm) e inglés.
_SIGNIN_KEYWORDS = (
    "código de acceso",
    "codigo de acceso",
    "código de un solo uso",
    "codigo de un solo uso",
    "código de un único uso",
    "código único",
    "codigo unico",
    "código de verificación",
    "codigo de verificacion",
    "código de seguridad",
    "codigo de seguridad",
    "código de inicio de sesión",
    "codigo de inicio de sesion",
    "one-time passcode",
    "one time passcode",
    "one-time password",
    "passcode",
    "verification code",
    "security code",
    "login code",
    "sign-in code",
    "single-use code",
)

_HUMAN = {
    "signin_code": "Código de inicio de sesión",
    "other": "Correo de Disney+",
}

# Quita etiquetas HTML para poder buscar el código en el texto visible.
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\u00a0]+")


@dataclass
class DisneyResult:
    kind: str
    subject: str = ""
    code: str = ""
    action_url: str = ""
    links: list[str] = field(default_factory=list)

    @property
    def human_kind(self) -> str:
        return _HUMAN.get(self.kind, _HUMAN["other"])

    @property
    def has_payload(self) -> bool:
        return bool(self.code or self.action_url)


def _to_text(html: str, text: str) -> str:
    if text:
        return text
    if not html:
        return ""
    cleaned = _TAG_RE.sub(" ", _html.unescape(html))
    return _WS_RE.sub(" ", cleaned)


def _classify(subject: str, body: str) -> str:
    haystack = f"{subject}\n{body}".lower()
    if any(kw in haystack for kw in _SIGNIN_KEYWORDS):
        return "signin_code"
    return "other"


def _extract_code(body_text: str) -> str:
    """Busca un código numérico visible (4 a 8 dígitos, se prefiere 6).

    Primero intenta uno cercano a la palabra 'código'/'code'/'passcode'; si no,
    cae al primer número de 6 dígitos del cuerpo (típico de Disney+).
    """
    low = body_text.lower()
    best = ""
    for m in re.finditer(r"(?<!\d)(\d{4,8})(?!\d)", body_text):
        digits = m.group(1)
        start = max(0, m.start() - 50)
        context = low[start : m.end() + 15]
        near_kw = any(
            kw in context for kw in ("código", "codigo", "code", "passcode", "acceso")
        )
        if near_kw:
            # Cerca de la palabra clave: si es de 6 dígitos lo damos ya.
            if len(digits) == 6:
                return digits
            if not best:
                best = digits
    if best:
        return best
    # Sin contexto: tomamos el primer número de 6 dígitos del cuerpo.
    m6 = re.search(r"(?<!\d)(\d{6})(?!\d)", body_text)
    return m6.group(1) if m6 else ""


def parse_disney_email(subject: str, html: str = "", text: str = "") -> DisneyResult:
    subject = subject or ""
    body_text = _to_text(html, text)
    kind = _classify(subject, body_text)
    code = _extract_code(body_text) if kind == "signin_code" else ""
    return DisneyResult(kind=kind, subject=subject.strip(), code=code)
