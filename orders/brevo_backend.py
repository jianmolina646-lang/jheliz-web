"""Backend de email de Django que envía vía la HTTP API de Brevo.

Muchos VPS bloquean los puertos SMTP de salida (25/465/587) para evitar
abuso. La API REST de Brevo viaja sobre HTTPS (443), así que funciona
incluso en hosts que filtran SMTP.

Configuración (en .env):
    EMAIL_BACKEND=orders.brevo_backend.BrevoEmailBackend
    BREVO_API_KEY=xkeysib-...
    DEFAULT_FROM_EMAIL=Jheliz <ecomercejheliz@gmail.com>

El remitente (el email del FROM) tiene que estar verificado previamente
en Brevo, sino la API responde 400.
"""

from __future__ import annotations

import logging
from email.utils import getaddresses, parseaddr
from typing import Iterable

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMessage

logger = logging.getLogger(__name__)

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
REQUEST_TIMEOUT = 15  # segundos


def _split_addr(value: str) -> dict:
    """Convierte 'Nombre <email@x.com>' en {'name': 'Nombre', 'email': '...'}.

    Si solo viene el email, devuelve {'email': '...'} (sin name).
    """
    name, email = parseaddr(value or "")
    if not email:
        return {}
    payload = {"email": email}
    if name:
        payload["name"] = name
    return payload


def _split_addr_list(values: Iterable[str]) -> list[dict]:
    out = []
    for parsed_name, parsed_email in getaddresses(list(values or [])):
        if not parsed_email:
            continue
        item = {"email": parsed_email}
        if parsed_name:
            item["name"] = parsed_name
        out.append(item)
    return out


class BrevoEmailBackend(BaseEmailBackend):
    """Email backend que envía cada ``EmailMessage`` por la API HTTP de Brevo."""

    def __init__(self, *, fail_silently: bool = False, api_key: str | None = None, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = api_key or getattr(settings, "BREVO_API_KEY", "") or ""

    def send_messages(self, email_messages):  # type: ignore[override]
        if not email_messages:
            return 0
        if not self.api_key:
            if self.fail_silently:
                return 0
            raise RuntimeError(
                "BREVO_API_KEY no está configurada. Definila en el .env o pasala al backend."
            )

        sent = 0
        session = requests.Session()
        session.headers.update({
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": self.api_key,
        })
        try:
            for msg in email_messages:
                if self._send_one(session, msg):
                    sent += 1
        finally:
            session.close()
        return sent

    # ------------------------------------------------------------------

    def _send_one(self, session: requests.Session, msg: EmailMessage) -> bool:
        payload = self._build_payload(msg)
        try:
            response = session.post(
                BREVO_ENDPOINT, json=payload, timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.exception("Brevo: error de red enviando a %s", msg.to)
            if not self.fail_silently:
                raise
            return False

        if response.status_code >= 400:
            body = (response.text or "")[:500]
            logger.error(
                "Brevo respondió %s para destino=%s: %s",
                response.status_code, msg.to, body,
            )
            if not self.fail_silently:
                # Levantamos una excepción común a Django (BadHeaderError o RuntimeError)
                raise RuntimeError(
                    f"Brevo HTTP {response.status_code}: {body}"
                )
            return False
        return True

    def _build_payload(self, msg: EmailMessage) -> dict:
        # Sender: respetar el from_email del mensaje; si está vacío, usar el
        # DEFAULT_FROM_EMAIL ya inyectado por Django (rara vez vacío).
        sender = _split_addr(msg.from_email or settings.DEFAULT_FROM_EMAIL)
        if not sender:
            raise RuntimeError(
                "El mensaje no tiene 'from' válido y DEFAULT_FROM_EMAIL tampoco."
            )

        to = _split_addr_list(msg.to)
        cc = _split_addr_list(msg.cc) if msg.cc else []
        bcc = _split_addr_list(msg.bcc) if msg.bcc else []
        reply_to = _split_addr(msg.reply_to[0]) if msg.reply_to else None

        # Body: si es HTML (subtype 'html'), va en htmlContent; sino, plano.
        body = msg.body or ""
        if (msg.content_subtype or "").lower() == "html":
            content_key = "htmlContent"
        else:
            content_key = "textContent"

        payload = {
            "sender": sender,
            "to": to,
            "subject": msg.subject or "",
            content_key: body,
        }
        if cc:
            payload["cc"] = cc
        if bcc:
            payload["bcc"] = bcc
        if reply_to:
            payload["replyTo"] = reply_to

        # Headers extra (ej. List-Unsubscribe si Django los agrega).
        if msg.extra_headers:
            payload["headers"] = {
                k: str(v) for k, v in msg.extra_headers.items()
            }
        return payload
