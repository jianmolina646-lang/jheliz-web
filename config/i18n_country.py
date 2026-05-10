"""Multi-país: middleware ligero, vista para cambiar de país, y context
processor que expone `request.country` + currency a todos los templates.

El idioma se maneja con `django.middleware.locale.LocaleMiddleware` y la
vista built-in `django.views.i18n.set_language` (montada en /i18n/setlang/).
Esto guarda la preferencia en la cookie `django_language`.

El país lo guardamos por separado en la cookie `jheliz_country` porque dos
países pueden compartir idioma (PE/CO/MX hablan español pero usan distinta
moneda y método de pago).
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponseRedirect, JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.views.decorators.http import require_POST


COUNTRY_COOKIE = "jheliz_country"
COUNTRY_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 año


def _country_map():
    return {c["code"]: c for c in getattr(settings, "COUNTRIES", [])}


def get_country(request) -> dict:
    """Devuelve el dict de país activo para este request.

    Resolución: cookie → header geo (CF-IPCountry / X-Country-Code) → DEFAULT_COUNTRY.
    """
    countries = _country_map()
    code = (
        (request.COOKIES.get(COUNTRY_COOKIE) or "").upper()
        or (request.META.get("HTTP_CF_IPCOUNTRY") or "").upper()
        or (request.META.get("HTTP_X_COUNTRY_CODE") or "").upper()
        or settings.DEFAULT_COUNTRY
    )
    return countries.get(code) or countries.get(settings.DEFAULT_COUNTRY) or {
        "code": "PE", "name": "Perú", "flag": "🇵🇪",
        "currency": "PEN", "symbol": "S/", "locale": "es", "phone_cc": "+51",
    }


class CountryMiddleware(MiddlewareMixin):
    """Inyecta `request.country` con el dict del país activo."""

    def process_request(self, request):
        request.country = get_country(request)
        return None


def country_context(request):
    """Context processor: expone country, currency_symbol, languages y
    countries a todos los templates."""
    country = getattr(request, "country", None) or get_country(request)
    return {
        "COUNTRY": country,
        "COUNTRY_CODE": country.get("code"),
        "COUNTRY_FLAG": country.get("flag"),
        "COUNTRY_CURRENCY": country.get("currency"),
        "COUNTRY_SYMBOL": country.get("symbol") or settings.DEFAULT_CURRENCY_SYMBOL,
        "AVAILABLE_COUNTRIES": getattr(settings, "COUNTRIES", []),
        "AVAILABLE_LANGUAGES": getattr(settings, "LANGUAGES", []),
    }


@require_POST
def set_country(request):
    """POST: { code: "PE" } → guarda cookie y redirige al next o /."""
    code = (request.POST.get("code") or "").upper().strip()
    valid = {c["code"] for c in getattr(settings, "COUNTRIES", [])}
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
    # Sanity: que el next sea relativo al sitio para evitar open-redirect.
    if not next_url.startswith("/"):
        next_url = "/"
    if code not in valid:
        return JsonResponse({"error": "país no soportado"}, status=400)
    response = HttpResponseRedirect(next_url)
    response.set_cookie(
        COUNTRY_COOKIE,
        code,
        max_age=COUNTRY_COOKIE_MAX_AGE,
        samesite="Lax",
    )
    return response
