"""Parser de los correos de Netflix.

Dado el asunto + cuerpo (HTML/texto) de un correo de Netflix, detecta de qué
tipo es y extrae lo accionable para el cliente:

- **signin_code**: "Tu código de inicio de sesión".
- **temp_code**: "Tu código de acceso temporal" (viajes / fuera del hogar).
  Trae un botón "Obtener código" con un link a netflix.com.
- **household**: "Cómo actualizar tu Hogar" / "Actualizar Hogar con Netflix".
  Trae un botón para confirmar el dispositivo/hogar.
- **password_reset**: "Restablece tu contraseña" / "Cómo restablecer tu
  contraseña". Trae un botón/link para crear una contraseña nueva.
- **tv_signin**: "Inicia sesión en tu TV" / "Es hora de ver Netflix".
  Trae un botón/link para activar Netflix en el televisor.
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
    r"https?://(?:[a-z0-9-]+\.)*netflix\.com/[^\s\"'<>)]+", re.IGNORECASE
)

# Palabras clave por tipo, en los idiomas más comunes (es, en, it, pt, fr,
# de). Las cuentas de Netflix pueden estar en cualquier país/idioma; cuando
# el idioma no está cubierto, ``_classify`` cae a los links de netflix.com
# (rutas iguales en todos los idiomas) vía ``_URL_HINTS``.
# El orden importa: ``_classify`` devuelve el primer tipo que matchea, así que
# los más específicos van primero.
_KEYWORDS = {
    "passwordless_signin": (
        "inicia sesión sin una contraseña",
        "inicia sesión sin contraseña",
        "iniciar sesión sin contraseña",
        "enlace de uso único",
        "enlace de un solo uso",
        "sign in without a password",
        "passwordless sign in",
        "one-time sign-in link",
        "one time sign in link",
    ),
    "tv_signin": (
        "inicia sesión en tu tv",
        "iniciar sesión en tu tv",
        "netflix en tu tv",
        "es hora de ver netflix",
        "finish signing in",
        "sign in to your tv",
        "/tv/out",
        "tv/signup",
        "accedi dalla tv",
        "entrar na tv",
    ),
    "temp_code": (
        "código de acceso temporal",
        "acceso temporal",
        "obtener código",
        "temporary access code",
        "codice di accesso temporaneo",
        "código de acesso temporário",
        "code d'accès temporaire",
        "temporärer zugangscode",
        "travel/verify",
    ),
    "household": (
        "actualizar tu hogar",
        "actualizar hogar",
        "hogar con netflix",
        "update household",
        "primary-location",
        "update-primary-location",
        "aggiorna il tuo domicilio",
        "aggiornare il domicilio",
        "atualizar residência",
        "atualizar a sua residência",
        "foyer netflix",
        "mettre à jour votre foyer",
        "netflix-haushalt",
    ),
    "password_reset": (
        "restablece tu contraseña",
        "restablecer tu contraseña",
        "restablecer contraseña",
        "restablecimiento de contraseña",
        "cambia tu contraseña",
        "olvidaste tu contraseña",
        "reset your password",
        "password-reset",
        "forgotpassword",
        "loginhelp",
        "reimposta la password",
        "redefinir senha",
        "redefinir sua senha",
        "réinitialiser votre mot de passe",
        "passwort zurücksetzen",
    ),
    "signin_code": (
        "código de inicio de sesión",
        "login code",
        "sign-in code",
        "codice di accesso",
        "codice per accedere",
        "código de acesso",
        "código para iniciar sesión",
        "code de connexion",
        "anmeldecode",
        "einmalcode",
    ),
}

# Pistas en la ruta del link para elegir el botón correcto.
_URL_HINTS = {
    "passwordless_signin": ("accountaccess", "passwordless", "magiclink"),
    "tv_signin": ("/tv", "tv/out", "tv-signin", "tv8", "/ilum"),
    "temp_code": ("travel", "verify", "otp", "temporary"),
    "household": ("update-primary-location", "primary-location", "household", "confirm"),
    "password_reset": ("password", "forgotpassword", "loginhelp", "reset"),
    "signin_code": ("login", "signin", "account/login"),
}

_HUMAN = {
    "passwordless_signin": "Enlace para iniciar sesión sin contraseña",
    "tv_signin": "Activar Netflix en tu TV",
    "temp_code": "Código de acceso temporal",
    "household": "Actualizar Hogar con Netflix",
    "password_reset": "Restablecer contraseña",
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


def _classify(subject: str, body: str, links: list[str] | None = None) -> str:
    haystack = f"{subject}\n{body}".lower()
    # Las solicitudes nuevas incluyen dos acciones distintas: /ilum aprueba
    # el acceso y /denysignin lo rechaza. Solo el enlace de aprobación se
    # entrega mediante ``enlace tv``; un aviso que tenga únicamente el botón
    # de rechazo continúa bloqueado.
    if "nueva solicitud de inicio de sesión" in haystack:
        if any("/ilum" in link.lower() for link in links or []):
            return "tv_signin"
        return "other"
    for kind, kws in _KEYWORDS.items():
        if any(kw in haystack for kw in kws):
            return kind
    # Fallback independiente del idioma: las rutas de los links de
    # netflix.com son iguales en todos los países.
    for kind, hints in _URL_HINTS.items():
        for link in links or []:
            low = link.lower()
            if any(h in low for h in hints):
                return kind
    return "other"


def _pick_action_url(kind: str, links: list[str]) -> str:
    if not links:
        return ""
    hints = _URL_HINTS.get(kind, ())
    for link in links:
        low = link.lower()
        if "/denysignin" in low:
            continue
        if any(h in low for h in hints):
            return link
    # Preferí un link de /account/ antes que uno de marketing/ayuda.
    for link in links:
        if "/denysignin" in link.lower():
            continue
        if "/account" in link.lower():
            return link
    return next((link for link in links if "/denysignin" not in link.lower()), "")


def _extract_code(kind: str, body_text: str) -> str:
    """Busca un código numérico visible (4 a 8 dígitos) cerca de 'código'.

    Muchos correos de acceso temporal NO traen el número (hay que abrir el
    link); por eso esto es best-effort y puede volver vacío.
    """
    if kind not in {"temp_code", "signin_code", "tv_signin"}:
        return ""
    # Número de 4-8 dígitos en una línea casi sola (típico del código).
    for m in re.finditer(r"(?<!\d)(\d{4,8})(?!\d)", body_text):
        start = max(0, m.start() - 40)
        context = body_text[start : m.end() + 10].lower()
        # "código" cubre es/pt; "cod" code/codice (en/it/fr); "kod" idiomas
        # germánicos/eslavos.
        if "código" in context or "cod" in context or "kod" in context:
            return m.group(1)
    # Fallback independiente del idioma: un número de 4-8 dígitos SOLO en
    # su propia línea (así muestran el código todos los correos de Netflix).
    m = re.search(r"^\s*(\d{4,8})\s*$", body_text, re.MULTILINE)
    return m.group(1) if m else ""


def _visible_html_text(value: str) -> str:
    """Convierte el HTML del correo en texto conservando cortes de bloque."""
    value = re.sub(
        r"(?i)</?(?:br|p|div|h[1-6]|li|tr|td|table)[^>]*>", "\n", value or ""
    )
    return _html.unescape(re.sub(r"<[^>]+>", "", value))


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

    kind = _classify(subject, f"{html}\n{text}", uniq_links)
    action_url = _pick_action_url(kind, uniq_links)
    # Algunos correos multipart traen un text/plain que es solo un preheader;
    # el código visible vive en el HTML. Analizamos ambos siempre.
    visible_body = "\n".join(part for part in (text, _visible_html_text(html)) if part)
    code = _extract_code(kind, visible_body)
    return NetflixResult(
        kind=kind,
        subject=subject.strip(),
        action_url=action_url,
        code=code,
        links=uniq_links,
    )
