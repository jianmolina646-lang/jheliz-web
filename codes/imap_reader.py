"""Lectura de las casillas centrales por IMAP.

A la casilla corporativa se reenvían los correos de Netflix de
todas las cuentas. Cuando un cliente pide el código de ``cuenta@gmail.com``,
buscamos el último correo de Netflix dirigido a ESE correo en TODAS las
casillas configuradas y devolvemos el más reciente.

Como los correos llegan reenviados, el destinatario original puede estar en
distintos headers (``To``, ``Delivered-To``, ``X-Forwarded-To``,
``Resent-To``…); los revisamos todos y, como último recurso, buscamos el
correo dentro del cuerpo.
"""

from __future__ import annotations

import email
import imaplib
import logging
import re
import ssl
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime

from django.conf import settings

from .disney import DisneyResult, parse_disney_email
from .netflix import NetflixResult, parse_netflix_email

logger = logging.getLogger(__name__)

# Cada servicio define con qué término se busca en la casilla y con qué parser
# se interpreta el correo. La casilla central es la misma (mismo Gmail); lo
# único que cambia es el término IMAP y el parser.
_SERVICES = {
    "netflix": ("netflix", parse_netflix_email),
    "disney": ("disney", parse_disney_email),
}

_RECIPIENT_HEADERS = (
    "To",
    "Cc",
    "Delivered-To",
    "X-Forwarded-To",
    "X-Forwarded-For",
    "X-Original-To",
    "Resent-To",
    "Envelope-To",
)


def _accounts() -> list[dict]:
    """Casillas centrales configuradas (principal + secundaria).

    La principal usa ``CODES_IMAP_*`` y la secundaria ``CODES_IMAP2_*``.
    Solo se incluyen las completas.
    """
    accounts: list[dict] = []
    for prefix in ("CODES_IMAP", "CODES_IMAP2"):
        host = getattr(settings, f"{prefix}_HOST", "")
        user = getattr(settings, f"{prefix}_USER", "")
        password = getattr(settings, f"{prefix}_PASSWORD", "")
        if host and user and password:
            accounts.append({
                "host": host,
                "port": getattr(settings, f"{prefix}_PORT", 993),
                "user": user,
                "password": password,
                "security": getattr(settings, f"{prefix}_SECURITY", "SSL").upper(),
                "tls_verify": getattr(settings, f"{prefix}_TLS_VERIFY", True),
            })
    return accounts


def is_configured() -> bool:
    return bool(_accounts())


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _recipients(msg: Message) -> set[str]:
    found: set[str] = set()
    for header in _RECIPIENT_HEADERS:
        raw = msg.get_all(header, [])
        for _name, addr in getaddresses(raw):
            if addr:
                found.add(addr.strip().lower())
    return found


def _bodies(msg: Message) -> tuple[str, str]:
    """Devuelve (html, text) del mensaje."""
    html, text = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_filename():
                continue
            ctype = part.get_content_type()
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                chunk = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if ctype == "text/html" and not html:
                html = chunk
            elif ctype == "text/plain" and not text:
                text = chunk
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            chunk = payload.decode(charset, errors="replace") if payload else ""
        except Exception:
            chunk = ""
        if msg.get_content_type() == "text/html":
            html = chunk
        else:
            text = chunk
    return html, text


_INTERNALDATE_RE = re.compile(
    rb'INTERNALDATE "(?P<value>\d{1,2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2}:\d{2} [+-]\d{4})"'
)


def _msg_datetime(msg: Message, fetch_metadata: bytes = b"") -> datetime | None:
    """Fecha real de recepción; nunca convierte un correo inválido en nuevo."""
    match = _INTERNALDATE_RE.search(fetch_metadata or b"")
    if match:
        try:
            return datetime.strptime(
                match.group("value").decode("ascii"), "%d-%b-%Y %H:%M:%S %z"
            ).astimezone(timezone.utc)
        except (UnicodeDecodeError, ValueError):
            pass
    try:
        dt = parsedate_to_datetime(msg.get("Date"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def fetch_latest_for_email(
    account_email: str,
    kind: str | None = None,
    lookback_minutes: int | None = None,
    service: str = "netflix",
) -> NetflixResult | DisneyResult | None:
    """Busca el último correo del ``service`` dirigido a ``account_email``.

    ``service`` elige el término de búsqueda y el parser (``netflix`` o
    ``disney``). Si se pasa ``kind``, solo se considera el correo más reciente
    de ESE tipo; los demás se ignoran. Sin ``kind`` se devuelve el más
    reciente de cualquier tipo reconocido.

    Devuelve el resultado parseado o ``None`` si no hay nada reciente que
    coincida.
    """
    accounts = _accounts()
    if not accounts:
        raise RuntimeError("IMAP de la casilla de códigos no configurado")

    try:
        search_term, parser = _SERVICES[service]
    except KeyError:
        raise ValueError(f"Servicio de códigos desconocido: {service!r}")

    account_email = (account_email or "").strip().lower()
    if not account_email:
        return None

    lookback = lookback_minutes or getattr(settings, "CODES_LOOKBACK_MINUTES", 30)
    since_dt = datetime.now(timezone.utc) - timedelta(minutes=lookback)

    candidates: list[tuple[datetime, NetflixResult | DisneyResult]] = []
    errors = 0
    for account in accounts:
        try:
            candidates.extend(
                _search_account(
                    account, account_email, search_term, parser, kind, since_dt
                )
            )
        except Exception:
            logger.exception("Fallo leyendo IMAP en %s", account["host"])
            errors += 1
    if errors == len(accounts):
        raise RuntimeError("Ninguna casilla de códigos respondió")
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _search_account(
    account: dict,
    account_email: str,
    search_term: str,
    parser,
    kind: str | None,
    since_dt: datetime,
) -> list[tuple[datetime, NetflixResult | DisneyResult]]:
    """Busca en UNA casilla y devuelve los candidatos (fecha, resultado)."""
    # IMAP SINCE tiene granularidad de día; afinamos por hora en Python.
    since_imap = (since_dt - timedelta(days=1)).strftime("%d-%b-%Y")

    timeout = getattr(settings, "CODES_IMAP_TIMEOUT", 20)
    security = account.get("security", "SSL")
    tls_context = ssl.create_default_context()
    if not account.get("tls_verify", True):
        # Solo para un proxy local de confianza (por ejemplo Proton Bridge).
        tls_context.check_hostname = False
        tls_context.verify_mode = ssl.CERT_NONE
    if security == "STARTTLS":
        conn = imaplib.IMAP4(account["host"], account["port"], timeout=timeout)
        conn.starttls(ssl_context=tls_context)
    elif security == "SSL":
        conn = imaplib.IMAP4_SSL(
            account["host"], account["port"], timeout=timeout, ssl_context=tls_context
        )
    else:
        raise ValueError(f"Seguridad IMAP no soportada: {security}")
    try:
        conn.login(account["user"], account["password"])
        # El bot solo consulta mensajes: nunca debe marcar, mover ni eliminar.
        conn.select("INBOX", readonly=True)
        # TEXT busca en todo el mensaje: agarra tanto los reenvíos automáticos
        # (From: el servicio) como los reenviados a mano (From: la cuenta
        # origen, con el correo del servicio dentro del cuerpo).
        typ, data = conn.search(None, "SINCE", since_imap, "TEXT", search_term)
        if typ != "OK":
            return []
        ids = data[0].split()
        # Recorremos de más nuevo a más viejo y solo los N más recientes:
        # no tiene sentido bajar correos viejos que ya cayeron fuera de la
        # ventana de minutos.
        max_scan = getattr(settings, "CODES_IMAP_MAX_SCAN", 25)
        ids = list(reversed(ids))[:max_scan]
        candidates: list[tuple[datetime, NetflixResult | DisneyResult]] = []
        for msg_id in ids:
            # INTERNALDATE es la fecha fiable del servidor; BODY.PEEK[] no
            # marca el correo como leído.
            typ, msg_data = conn.fetch(msg_id, "(INTERNALDATE BODY.PEEK[])")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            metadata, raw = msg_data[0]
            msg = email.message_from_bytes(raw)
            dt = _msg_datetime(msg, metadata)
            if dt is None or dt < since_dt:
                continue
            recipients = _recipients(msg)
            html, text = _bodies(msg)
            matches = account_email in recipients or account_email in raw.decode(
                "utf-8", errors="replace"
            ).lower()
            if not matches:
                continue
            subject = _decode(msg.get("Subject"))
            result = parser(subject, html=html, text=text)
            # Sin tipo puntual solo se consideran mensajes reconocidos por el
            # parser. Avisos comerciales, cambios de correo y cualquier otro
            # mensaje de Netflix clasificado como ``other`` nunca se entrega.
            if kind is None and result.kind == "other":
                continue
            # Cuando se pide un tipo puntual, solo entregamos ese tipo;
            # cualquier otro correo del servicio se ignora.
            if kind is not None and result.kind != kind:
                continue
            # Con tipo puntual, el primer match (ya vamos de más nuevo a más
            # viejo) es el más reciente de ESTA casilla: cortamos acá y la
            # comparación entre casillas se hace por fecha más arriba.
            candidates.append((dt, result))
            if kind is not None:
                return candidates
        return candidates
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            conn.logout()
        except Exception:
            pass
