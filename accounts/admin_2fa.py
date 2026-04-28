"""Enforcement opcional de 2FA (TOTP) en el panel de admin.

Activado por la variable de entorno ``ADMIN_2FA_ENFORCED`` (default: False).

Cuando está activado:
- El admin sigue mostrando el formulario de login normal (usuario+contraseña).
- Una vez logueado, ``has_permission`` exige que el request esté
  ``is_verified()`` (es decir, que haya un dispositivo OTP confirmado en
  esta sesión). Si no, redirige a la página de gestión de TOTP donde el
  superuser puede registrar su dispositivo.

Cuando está desactivado:
- El admin funciona como siempre. El stack ``django-otp`` queda instalado
  pero no obliga 2FA, dándote tiempo a registrar tu TOTP sin riesgo de
  bloquearte fuera.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib import admin


def _patch_admin_site_for_otp() -> None:
    site = admin.site
    original_has_permission = site.has_permission

    def has_permission(request) -> bool:
        if not original_has_permission(request):
            return False
        user = request.user
        if not (user.is_active and user.is_staff):
            return False
        # Exigir verificación OTP sólo si está activo el flag.
        if getattr(settings, "ADMIN_2FA_ENFORCED", False):
            return bool(getattr(user, "is_verified", lambda: False)())
        return True

    site.has_permission = has_permission  # type: ignore[method-assign]

    # Cuando 2FA es obligatorio, el form de login necesita pedir el código
    # TOTP además de usuario/contraseña. django-otp provee
    # OTPAuthenticationForm que añade el campo "OTP token" al formulario.
    if getattr(settings, "ADMIN_2FA_ENFORCED", False):
        try:
            from django_otp.forms import OTPAuthenticationForm

            site.login_form = OTPAuthenticationForm
        except ImportError:  # pragma: no cover
            pass


_patch_admin_site_for_otp()
