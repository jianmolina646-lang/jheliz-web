"""Backend SMTP que obliga a usar el remitente corporativo autorizado."""

from email.utils import parseaddr

from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend
from django.core.mail.message import sanitize_address


class CorporateSMTPEmailBackend(SMTPEmailBackend):
    """Normaliza todos los mensajes al único remitente corporativo permitido."""

    def send_messages(self, email_messages):
        authorized = settings.DEFAULT_FROM_EMAIL
        authorized_address = parseaddr(authorized)[1].lower()
        if not authorized_address:
            raise RuntimeError("DEFAULT_FROM_EMAIL no contiene un correo válido")
        for message in email_messages or ():
            message.from_email = authorized
            # Impide que headers manuales suplanten otra identidad de origen.
            for header in ("From", "Sender", "Return-Path"):
                message.extra_headers.pop(header, None)
            sanitize_address(authorized, message.encoding or settings.DEFAULT_CHARSET)
        return super().send_messages(email_messages)
