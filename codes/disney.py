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
# Bloques cuyo contenido NO es texto visible (los colores CSS como #707070 se
# colaban como falsos "códigos"). Se eliminan por completo antes de leer.
_NONVISIBLE_RE = re.compile(r"(?is)<(style|script|head)[^>]*>.*?</\1>")

# Palabras que aparecen cerca del código real (suben el puntaje del candidato).
_CODE_POS_KW = (
    "código",
    "codigo",
    "code",
    "passcode",
    "acceso",
    "verificación",
    "verificacion",
    "one-time",
    "one time",
    "single-use",
    "un solo uso",
    "único uso",
    "unico uso",
    "expire",
    "expira",
    "vence",
    "minute",
    "minuto",
)
# Palabras que descartan un número (registro de la empresa, direcciones, tel.).
_CODE_NEG_KW = (
    "registered",
    "registro",
    "registration",
    "reg. no",
    "reg no",
    "no.",
    "copyright",
    "street",
    "avenue",
    "suite",
    "floor",
    "p.o",
    "zip",
    "phone",
    "tel",
    "unsubscribe",
)


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


def _visible_from_html(html: str) -> str:
    cleaned = _NONVISIBLE_RE.sub(" ", html)
    cleaned = _TAG_RE.sub(" ", _html.unescape(cleaned))
    return _WS_RE.sub(" ", cleaned)


def _to_text(html: str, text: str) -> str:
    """Combina texto plano y texto visible del HTML.

    Se incluyen ambos porque el text/plain de Disney+ suele venir vacío (o ser
    solo un preheader) y el código vive en el HTML. Al armar el texto visible
    se eliminan los bloques <style>/<head>/<script> para que los colores CSS
    (p. ej. #707070) no se confundan con el código.
    """
    parts: list[str] = []
    if text and text.strip():
        parts.append(text)
    if html:
        parts.append(_visible_from_html(html))
    return "\n".join(parts)


def _classify(subject: str, body: str) -> str:
    haystack = f"{subject}\n{body}".lower()
    if any(kw in haystack for kw in _SIGNIN_KEYWORDS):
        return "signin_code"
    return "other"


def _extract_code(body_text: str) -> str:
    """Busca el código numérico (4 a 8 dígitos, se prefiere 6).

    Puntúa cada número por su contexto: suma si está cerca de palabras como
    'código'/'passcode'/'expira'; descarta los que están en el pie legal
    ('Registered No.'), direcciones o teléfonos, y los colores hex (#707070).
    Se elige el de mayor puntaje y, a igualdad, el que aparece primero.
    """
    low = body_text.lower()
    candidates: list[tuple[int, int, str]] = []
    for m in re.finditer(r"(?<!\d)(\d{4,8})(?!\d)", body_text):
        # Descarta colores hex tipo #707070.
        if m.start() > 0 and body_text[m.start() - 1] == "#":
            continue
        digits = m.group(1)
        start = max(0, m.start() - 60)
        context = low[start : m.end() + 25]
        if any(kw in context for kw in _CODE_NEG_KW):
            continue
        score = 0
        if any(kw in context for kw in _CODE_POS_KW):
            score += 10
        if len(digits) == 6:
            score += 3
        # (-puntaje, posición) → menor es mejor: mayor puntaje y antes en el texto.
        candidates.append((-score, m.start(), digits))
    if not candidates:
        return ""
    candidates.sort()
    return candidates[0][2]


def parse_disney_email(subject: str, html: str = "", text: str = "") -> DisneyResult:
    subject = subject or ""
    body_text = _to_text(html, text)
    kind = _classify(subject, body_text)
    code = _extract_code(body_text) if kind == "signin_code" else ""
    return DisneyResult(kind=kind, subject=subject.strip(), code=code)
