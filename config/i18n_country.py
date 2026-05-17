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
from django.utils import translation
from django.utils.deprecation import MiddlewareMixin
from django.views.decorators.http import require_POST


COUNTRY_COOKIE = "jheliz_country"
COUNTRY_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 año
# Cookie nombre estandar que usa Django para el idioma.
LANGUAGE_COOKIE = "django_language"

# Paises hispanohablantes (sirven el sitio en espanol + PEN/su moneda).
SPANISH_COUNTRIES = {"PE", "CO", "MX", "AR", "CL", "EC", "BO", "VE", "UY", "PY", "DO", "GT", "HN", "SV", "NI", "CR", "PA", "CU", "ES"}
# Pais lusofono.
PORTUGUESE_COUNTRIES = {"BR", "PT", "AO", "MZ"}


def language_for_country(code: str | None) -> str:
    """Devuelve el codigo de idioma sugerido para un pais.

    Reglas:
    - LatAm + Espana hispanohablante → 'es'
    - Brasil/Portugal lusofono → 'pt'
    - Cualquier otro pais → 'en' (default internacional)
    """
    if not code:
        return "es"  # default: espanol (mercado principal)
    c = code.upper()
    if c in SPANISH_COUNTRIES:
        return "es"
    if c in PORTUGUESE_COUNTRIES:
        return "pt"
    return "en"


def display_currency_for_country(code: str | None) -> str:
    """Moneda VISIBLE para mostrar al usuario.

    - Peru → PEN (todo en S/)
    - Otros → USD (todo en USD usando el TC de Binance P2P)

    El pago real se cobra con Yape (PEN) o Binance Pay / Lemon Squeezy (USD)
    segun lo elija el cliente. Esto solo afecta el display.
    """
    if (code or "").upper() == "PE":
        return "PEN"
    return "USD"


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
    """Inyecta `request.country` y autoselecciona idioma segun el pais.

    Si el usuario nunca toco el switcher (no tiene cookie `django_language`),
    activamos el idioma sugerido para su pais (PE→es, BR→pt, resto→en). Si
    ya tiene cookie de idioma se respeta esa eleccion explicita.
    """

    def process_request(self, request):
        request.country = get_country(request)
        # Solo auto-activamos idioma si el usuario NO eligio uno manualmente.
        if not request.COOKIES.get(LANGUAGE_COOKIE):
            # Para el idioma usamos el header geo crudo (no `request.country`),
            # asi un visitante de FR/DE/IT que no este en COUNTRIES igual ve EN
            # en vez del fallback a PE → es.
            raw_cc = (
                (request.COOKIES.get(COUNTRY_COOKIE) or "").upper()
                or (request.META.get("HTTP_CF_IPCOUNTRY") or "").upper()
                or (request.META.get("HTTP_X_COUNTRY_CODE") or "").upper()
                or request.country.get("code")
            )
            suggested = language_for_country(raw_cc)
            supported = {code for code, _ in getattr(settings, "LANGUAGES", [])}
            if suggested in supported:
                translation.activate(suggested)
                request.LANGUAGE_CODE = suggested
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
