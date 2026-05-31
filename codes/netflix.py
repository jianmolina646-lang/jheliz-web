"""Parser de los correos de Netflix.

Dado el asunto + cuerpo (HTML/texto) de un correo de Netflix, detecta de qué
tipo es y extrae lo accionable para el cliente:

- **temp_code**: "Tu código de acceso temporal" (viajes / fuera del hogar).
  Trae un botón "Obtener código" con un link a netflix.com.
- **household**: "Cómo actualizar tu Hogar" / "Actualizar Hogar con Netflix".
  Trae un botón para confirmar el dispositivo/hogar.
- **signin_code**: "Tu código de inicio de sesión".
- **other**: correo de Netflix no reconocido.

El resultado siempre incluye el ``action_url`` (link del botón principal)
cuando se puede encontrar, y ``code`` si el correo trae un número visible.

NOTA: los formatos exactos de Netflix cambian y varían por idioma. El
clasificador se basa en palabras clave del asunto y en la ruta de los links
de netflix.com; está pensado para refinarse con muestras reales.
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field

# Links de acción de netflix.com (los que llevan a confirmar/obtener código).
_NETFLIX_LINK_RE = re.compile(
    r"https?://[a-z0-9.\-]*netflix\.com/[^\s\"'<>)]+", re.IGNORECASE
)

# Palabras clave por tipo (en español; se cubren variantes comunes).
_KEYWORDS = {
    "temp_code": ("código de acceso temporal", "acceso temporal", "obtener código"),
    "household": (
        "actualizar tu hogar",
        "actualizar hogar",
        "hogar con netflix",
        "update household",
        "primary-location",
        "update-primary-location",
    ),
    "signin_code": ("código de inicio de sesión", "login code", "sign-in code"),
}

# Pistas en la ruta del link para elegir el botón correcto.
_URL_HINTS = {
    "temp_code": ("travel", "verify", "otp", "temporary"),
    "household": ("update-primary-location", "primary-location", "household", "confirm"),
    "signin_code": ("login", "signin", "account/login"),
}

_HUMAN = {
    "temp_code": "Código de acceso temporal",
    "household": "Actualizar Hogar con Netflix",
    "signin_code": "Código de inicio de sesión",
    "other": "Correo de Netflix",
}


@dataclass
class NetflixResult:
    kind: str
    subject: str = ""
    action_url: str = ""
    code: str = ""
    links: list[str] = field(default_factory=list)

    @property
    def human_kind(self) -> str:
        return _HUMAN.get(self.kind, _HUMAN["other"])

    @property
    def has_payload(self) -> bool:
        return bool(self.action_url or self.code)


def _classify(subject: str, body: str) -> str:
    haystack = f"{subject}\n{body}".lower()
    for kind, kws in _KEYWORDS.items():
        if any(kw in haystack for kw in kws):
            return kind
    return "other"


def _pick_action_url(kind: str, links: list[str]) -> str:
    if not links:
        return ""
    hints = _URL_HINTS.get(kind, ())
    for link in links:
        low = link.lower()
        if any(h in low for h in hints):
            return link
    # Preferí un link de /account/ antes que uno de marketing/ayuda.
    for link in links:
        if "/account" in link.lower():
            return link
    return links[0]


def _extract_code(kind: str, body_text: str) -> str:
    """Busca un código numérico visible (4 a 8 dígitos) cerca de 'código'.

    Muchos correos de acceso temporal NO traen el número (hay que abrir el
    link); por eso esto es best-effort y puede volver vacío.
    """
    if kind not in {"temp_code", "signin_code"}:
        return ""
    # Número de 4-8 dígitos en una línea casi sola (típico del código).
    for m in re.finditer(r"(?<!\d)(\d{4,8})(?!\d)", body_text):
        start = max(0, m.start() - 40)
        context = body_text[start : m.end() + 10].lower()
        if "código" in context or "code" in context:
            return m.group(1)
    return ""


def parse_netflix_email(subject: str, html: str = "", text: str = "") -> NetflixResult:
    subject = subject or ""
    body_for_links = html or text or ""
    links = _NETFLIX_LINK_RE.findall(body_for_links)
    # Dedup preservando orden.
    seen: set[str] = set()
    uniq_links = []
    for link in links:
        # Limpia entidades HTML (&amp; -> &) y puntuación final.
        link = _html.unescape(link).rstrip(".,)")
        if link not in seen:
            seen.add(link)
            uniq_links.append(link)

    kind = _classify(subject, f"{html}\n{text}")
    action_url = _pick_action_url(kind, uniq_links)
    code = _extract_code(kind, text or html)
    return NetflixResult(
        kind=kind,
        subject=subject.strip(),
        action_url=action_url,
        code=code,
        links=uniq_links,
    )
