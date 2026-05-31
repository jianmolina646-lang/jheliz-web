"""Lectura de la casilla central por IMAP.

A esta casilla (un Gmail) se reenvían los correos de Netflix de todas las
cuentas. Cuando un cliente pide el código de ``cuenta@gmail.com``, buscamos
el último correo de Netflix dirigido a ESE correo y lo parseamos.

Como los correos llegan reenviados, el destinatario original puede estar en
distintos headers (``To``, ``Delivered-To``, ``X-Forwarded-To``,
``Resent-To``…); los revisamos todos y, como último recurso, buscamos el
correo dentro del cuerpo.
"""

from __future__ import annotations

import email
import imaplib
import logging
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime

from django.conf import settings

from .netflix import NetflixResult, parse_netflix_email

logger = logging.getLogger(__name__)

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


def is_configured() -> bool:
    return bool(
        getattr(settings, "CODES_IMAP_USER", "")
        and getattr(settings, "CODES_IMAP_PASSWORD", "")
        and getattr(settings, "CODES_IMAP_HOST", "")
    )


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


def _msg_datetime(msg: Message) -> datetime:
    try:
        dt = parsedate_to_datetime(msg.get("Date"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


def fetch_latest_for_email(
    account_email: str,
    kind: str | None = None,
    lookback_minutes: int | None = None,
) -> NetflixResult | None:
    """Busca el último correo de Netflix dirigido a ``account_email``.

    Si se pasa ``kind`` (``signin_code`` / ``temp_code`` / ``household`` /
    ``password_reset``), solo se considera el correo más reciente de ESE tipo;
    los demás correos de Netflix se ignoran. Sin ``kind`` se devuelve el más
    reciente de cualquier tipo reconocido.

    Devuelve un :class:`~codes.netflix.NetflixResult` o ``None`` si no hay
    nada reciente que coincida.
    """
    if not is_configured():
        raise RuntimeError("IMAP de la casilla de códigos no configurado")

    account_email = (account_email or "").strip().lower()
    if not account_email:
        return None

    lookback = lookback_minutes or getattr(settings, "CODES_LOOKBACK_MINUTES", 30)
    since_dt = datetime.now(timezone.utc) - timedelta(minutes=lookback)
    # IMAP SINCE tiene granularidad de día; afinamos por hora en Python.
    since_imap = (since_dt - timedelta(days=1)).strftime("%d-%b-%Y")

    conn = imaplib.IMAP4_SSL(
        settings.CODES_IMAP_HOST, getattr(settings, "CODES_IMAP_PORT", 993)
    )
    try:
        conn.login(settings.CODES_IMAP_USER, settings.CODES_IMAP_PASSWORD)
        conn.select("INBOX")
        # TEXT busca en todo el mensaje: agarra tanto los reenvíos automáticos
        # (From: Netflix) como los reenviados a mano (From: la cuenta origen,
        # con el correo de Netflix dentro del cuerpo).
        typ, data = conn.search(None, "SINCE", since_imap, "TEXT", "netflix")
        if typ != "OK":
            return None
        ids = data[0].split()
        candidates: list[tuple[datetime, NetflixResult]] = []
        # Recorremos de más nuevo a más viejo.
        for msg_id in reversed(ids):
            typ, msg_data = conn.fetch(msg_id, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            dt = _msg_datetime(msg)
            if dt < since_dt:
                continue
            recipients = _recipients(msg)
            html, text = _bodies(msg)
            matches = account_email in recipients or account_email in raw.decode(
                "utf-8", errors="replace"
            ).lower()
            if not matches:
                continue
            subject = _decode(msg.get("Subject"))
            result = parse_netflix_email(subject, html=html, text=text)
            # Cuando se pide un tipo puntual (uno de los 4 comandos), solo
            # entregamos ese tipo; cualquier otro correo de Netflix se ignora.
            if kind is not None and result.kind != kind:
                continue
            candidates.append((dt, result))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            conn.logout()
        except Exception:
            pass
