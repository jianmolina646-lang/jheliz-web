from __future__ import annotations

import logging
import secrets
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)
SESSION_KEY = "password_reset_challenge"
CODE_TTL_SECONDS = 600
MAX_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60


@require_http_methods(["GET", "POST"])
def request_code(request):
    context: dict[str, object] = {}
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        now = int(time.time())
        previous = request.session.get(SESSION_KEY, {})
        if now - int(previous.get("sent_at", 0)) < RESEND_COOLDOWN_SECONDS:
            context["error"] = "Espera un minuto antes de solicitar otro código."
            return render(request, "accounts/password_reset_request.html", context)
        user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
        if user:
            code = f"{secrets.randbelow(1_000_000):06d}"
            request.session[SESSION_KEY] = {"user_id": str(user.pk), "code_hash": make_password(code), "expires_at": now + CODE_TTL_SECONDS, "sent_at": now, "attempts": 0}
            try:
                send_mail("Código para cambiar tu contraseña · Jheliz Digital", f"Tu código de recuperación es: {code}\n\nCaduca en 10 minutos y solo puede utilizarse una vez.\nSi no solicitaste este cambio, ignora este mensaje.", settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
            except Exception:
                request.session.pop(SESSION_KEY, None)
                logger.exception("No se pudo enviar el código de recuperación")
                context["error"] = "No se pudo enviar el código. Inténtalo nuevamente."
                return render(request, "accounts/password_reset_request.html", context)
        else:
            request.session[SESSION_KEY] = {"sent_at": now, "unknown": True}
        request.session.modified = True
        return redirect("password_reset_verify")
    return render(request, "accounts/password_reset_request.html", context)


@require_http_methods(["GET", "POST"])
def verify_code(request):
    challenge = request.session.get(SESSION_KEY)
    if not challenge:
        return redirect("password_reset_request")
    context: dict[str, object] = {}
    if challenge.get("unknown"):
        context["notice"] = "Si el correo está registrado, recibirás un código. Revisa también la carpeta de spam."
        return render(request, "accounts/password_reset_verify.html", context)
    if int(time.time()) > int(challenge.get("expires_at", 0)):
        request.session.pop(SESSION_KEY, None)
        return render(request, "accounts/password_reset_request.html", {"error": "El código caducó. Solicita uno nuevo."})
    if request.method == "POST":
        attempts = int(challenge.get("attempts", 0)) + 1
        challenge["attempts"] = attempts
        request.session[SESSION_KEY] = challenge
        request.session.modified = True
        if attempts > MAX_ATTEMPTS:
            request.session.pop(SESSION_KEY, None)
            return render(request, "accounts/password_reset_request.html", {"error": "Se superó el número de intentos. Solicita un código nuevo."})
        code = "".join(filter(str.isdigit, request.POST.get("code", "")))
        password1 = request.POST.get("password1", "")
        password2 = request.POST.get("password2", "")
        if len(code) != 6 or not check_password(code, challenge.get("code_hash", "")):
            context["error"] = "El código no es válido."
        elif password1 != password2:
            context["error"] = "Las contraseñas no coinciden."
        else:
            user = get_user_model().objects.filter(pk=challenge.get("user_id"), is_active=True).first()
            if not user:
                request.session.pop(SESSION_KEY, None)
                return redirect("password_reset_request")
            try:
                validate_password(password1, user=user)
            except ValidationError as exc:
                context["error"] = " ".join(exc.messages)
            else:
                user.set_password(password1)
                user.save(update_fields=["password"])
                request.session.pop(SESSION_KEY, None)
                request.session.cycle_key()
                return redirect("password_reset_complete")
    return render(request, "accounts/password_reset_verify.html", context)


@require_http_methods(["GET"])
def complete(request):
    return render(request, "accounts/password_reset_complete.html")
