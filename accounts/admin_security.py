"""Hardenings extra del login del admin: honeypot anti-bot + notificación.

Se activa al cargar la app `accounts` (ver ``apps.py``):

- ``HoneypotAdminAuthenticationForm``: agrega un campo invisible
  (``website``) que los humanos nunca llenan pero los bots de scraping sí.
  Si llega lleno, rechazamos el login con mensaje genérico ("credenciales
  inválidas") para no levantar sospechas.

- ``notify_admin_login``: handler de la señal ``user_logged_in`` de Django.
  Cuando un staff entra al admin, mandamos:
    1. Email a ``SUPPORT_ADMIN_EMAIL`` con: usuario, IP, ciudad, hora.
    2. Telegram al ``TELEGRAM_ADMIN_CHAT_ID`` con la misma info.

  Si recibís este mensaje y NO fuiste vos, sabés al toque que tu password
  se filtró → cambiá la clave inmediatamente. Se controla con el flag
  ``ADMIN_LOGIN_NOTIFY`` (default ``True``).
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.signals import user_logged_in
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Honeypot anti-bot
# ---------------------------------------------------------------------------


class HoneypotAdminAuthenticationForm(AdminAuthenticationForm):
    """Form de admin con un campo trampa invisible para humanos.

    El template oculta el campo con CSS (``display:none``) Y con
    ``tabindex="-1"`` + ``autocomplete="off"``. Un bot que itera sobre
    ``<input>`` lo va a llenar; un humano nunca lo verá.
    """

    def clean(self):
        # Honeypot: rechazar antes de hacer query a la DB para no gastar
        # recursos en bots.
        honey = self.data.get("website", "")
        if honey:
            logger.warning(
                "Honeypot disparado en admin login (ip=%s, ua=%s, valor=%s)",
                self._client_ip(),
                self._user_agent(),
                honey[:80],
            )
            # Mensaje genérico — no le decimos al bot que lo detectamos.
            raise ValidationError(
                self.error_messages["invalid_login"],
                code="invalid_login",
                params={"username": self.username_field.verbose_name},
            )
        return super().clean()

    # Helpers para logging.
    def _client_ip(self) -> str:
        req = self.request
        if not req:
            return "?"
        xff = req.META.get("HTTP_X_FORWARDED_FOR", "")
        if xff:
            return xff.split(",")[0].strip()
        return req.META.get("REMOTE_ADDR", "?")

    def _user_agent(self) -> str:
        req = self.request
        if not req:
            return "?"
        return (req.META.get("HTTP_USER_AGENT", "?") or "?")[:120]


# ---------------------------------------------------------------------------
# Notificación al login (email + Telegram)
# ---------------------------------------------------------------------------


def _client_ip(request) -> str:
    if not request:
        return "?"
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "?")


def _user_agent_short(request) -> str:
    if not request:
        return "?"
    ua = request.META.get("HTTP_USER_AGENT", "") or ""
    return ua[:120]


def _is_admin_request(request) -> bool:
    """Heurística para saber si el login viene del panel admin.

    No tenemos forma 100% confiable porque la señal se dispara después de
    autenticar; usamos el path actual + un fallback (siempre que sea staff).
    """
    if request is None:
        return False
    path = request.path or ""
    admin_prefix = f"/{getattr(settings, 'ADMIN_URL_PATH', 'panel-virtualidadsp')}/"
    return path.startswith(admin_prefix) or path.endswith("/login/")


@receiver(user_logged_in)
def notify_admin_login(sender, request, user, **kwargs: Any) -> None:
    """Manda email + Telegram cuando un staff inicia sesión en el admin."""
    if not getattr(user, "is_staff", False):
        return  # solo staff

    # Guardamos el ``last_login`` previo en la sesión ANTES de que Django
    # lo sobrescriba. Lo usamos en el index del admin para mostrar
    # "Tu última sesión fue: ...".
    if request is not None and getattr(user, "last_login", None):
        try:
            request.session["jheliz_previous_login"] = user.last_login.isoformat()
            request.session["jheliz_previous_login_ip"] = _client_ip(request)
        except Exception:  # pragma: no cover
            pass

    if not getattr(settings, "ADMIN_LOGIN_NOTIFY", True):
        return
    if not _is_admin_request(request):
        return  # ignoramos logins del front público

    ip = _client_ip(request)
    ua = _user_agent_short(request)
    when = timezone.localtime().strftime("%d/%m/%Y %H:%M:%S")
    username = getattr(user, "get_username", lambda: str(user))()
    email = getattr(user, "email", "") or ""

    subject = f"🔐 Nuevo inicio de sesión en el admin de VirtualidadSP ({username})"
    body = (
        f"Alguien acaba de iniciar sesión en tu panel admin.\n\n"
        f"• Usuario: {username}\n"
        f"• Email: {email or '(sin email)'}\n"
        f"• Hora: {when}\n"
        f"• IP: {ip}\n"
        f"• Dispositivo: {ua}\n\n"
        f"Si NO fuiste vos, cambiá tu contraseña inmediatamente y revisá los\n"
        f"logs en /panel-virtualidadsp/auditoria/.\n"
    )

    # Email.
    admin_email = getattr(settings, "SUPPORT_ADMIN_EMAIL", "") or getattr(
        settings, "DEFAULT_FROM_EMAIL", ""
    )
    if admin_email:
        try:
            send_mail(
                subject,
                body,
                getattr(settings, "DEFAULT_FROM_EMAIL", admin_email),
                [admin_email],
                fail_silently=True,
            )
        except Exception:  # pragma: no cover
            logger.exception("Fallo enviando notificación de login admin")

    # Telegram.
    try:
        from orders.telegram import is_configured, send_message  # type: ignore
        from orders.telegram import _admin_chat_id  # noqa: PLC2701

        chat_id = _admin_chat_id()
        if is_configured() and chat_id:
            send_message(
                chat_id,
                (
                    f"🔐 <b>Login admin</b>\n"
                    f"Usuario: <code>{username}</code>\n"
                    f"Hora: {when}\n"
                    f"IP: <code>{ip}</code>\n"
                    f"<i>Si no fuiste vos, cambiá tu contraseña ya.</i>"
                ),
            )
    except Exception:  # pragma: no cover
        logger.exception("Fallo enviando notificación Telegram de login admin")


# ---------------------------------------------------------------------------
# Patch del admin site para usar el form con honeypot
# ---------------------------------------------------------------------------


def _install_honeypot_form() -> None:
    """Reemplaza el ``login_form`` del admin por la versión con honeypot.

    Si ``ADMIN_2FA_ENFORCED=True``, el patch de ``accounts.admin_2fa`` ya
    sustituyó el form por ``OTPAuthenticationForm`` — en ese caso lo
    envolvemos para mantener honeypot + OTP juntos.
    """
    from django.contrib import admin

    site = admin.site
    base_form = site.login_form or AdminAuthenticationForm

    class _MergedForm(HoneypotAdminAuthenticationForm, base_form):  # type: ignore[misc, valid-type]
        pass

    site.login_form = _MergedForm  # type: ignore[assignment]


_install_honeypot_form()
