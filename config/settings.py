"""
Django settings for JhelizTV.
"""

from pathlib import Path

import dj_database_url
from decouple import Csv, config
from django.core.exceptions import ImproperlyConfigured

from config.secret_config import secret_config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = secret_config("SECRET_KEY", default="dev-insecure-key-change-me")
DEBUG = config("DEBUG", default=True, cast=bool)
if not DEBUG and SECRET_KEY == "dev-insecure-key-change-me":
    raise ImproperlyConfigured(
        "SECRET_KEY debe configurarse explícitamente cuando DEBUG=False."
    )
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default=(
        "127.0.0.1,localhost,ecormecejhelizstore.com,www.ecormecejhelizstore.com,"
        "jheliztv.xyz,www.jheliztv.xyz,"
        "jheliztv.xyz,www.jheliztv.xyz"
    ),
    cast=Csv(),
)

# Hosts que sirven el producto SaaS "Jheliz Control TV" (ruteo por dominio).
JHELIZTV_HOSTS = config(
    "JHELIZTV_HOSTS",
    default="jheliztv.xyz,www.jheliztv.xyz",
    cast=Csv(),
)
ALLOWED_HOSTS = list(dict.fromkeys([*ALLOWED_HOSTS, *JHELIZTV_HOSTS]))
SITE_URL = config("SITE_URL", default="http://127.0.0.1:8000")

# URL base del panel admin. Cambiá esto en .env para "esconder" el admin
# de bots que escanean rutas conocidas (/admin/, /wp-admin/, etc.). El
# valor NO debe llevar barras al inicio o al final.
ADMIN_URL_PATH = config("ADMIN_URL_PATH", default="panel-jheliz-control").strip("/")

CSRF_TRUSTED_ORIGINS = [
    "https://ecormecejhelizstore.com",
    "https://www.ecormecejhelizstore.com",
    "https://jheliztv.xyz",
    "https://www.jheliztv.xyz",
    "https://jheliztv.xyz",
    "https://www.jheliztv.xyz",
]

# Ante un token CSRF vencido (formulario viejo / botón "atrás"), recargar el
# formulario con un aviso en vez de mostrar la pantalla "Prohibido (403)".
CSRF_FAILURE_VIEW = "config.csrf_views.csrf_failure"

INSTALLED_APPS = [
    # Unfold debe ir ANTES de django.contrib.admin
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "unfold.contrib.import_export",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sitemaps",
    # Third-party
    "widget_tweaks",
    "django_htmx",
    "axes",  # protección anti fuerza-bruta en el login
    "django_otp",  # base para 2FA
    "django_otp.plugins.otp_totp",  # TOTP (Google Authenticator / Authy / 1Password)
    "django_otp.plugins.otp_static",  # códigos de respaldo
    "auditlog",  # registro de cambios (quién hizo qué, cuándo)
    "csp",  # Content Security Policy
    "import_export",  # CSV/XLSX import-export en el admin
    # Local
    "accounts.apps.AccountsConfig",
    "catalog.apps.CatalogConfig",
    "orders.apps.OrdersConfig",
    "support.apps.SupportConfig",
    "blog.apps.BlogConfig",
    "discord_bot.apps.DiscordBotConfig",
    "livechat.apps.LivechatConfig",
    "codes.apps.CodesConfig",
    "gestion.apps.GestionConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Ruteo por dominio: jheliztv.xyz sirve el producto SaaS (JhelizTV Control).
    "config.host_routing.JheliztvHostMiddleware",
    # i18n: detecta el idioma del usuario (cookie / header / sesión).
    "django.middleware.locale.LocaleMiddleware",
    # multi-país: inyecta `request.country` con el dict del país activo.
    "config.i18n_country.CountryMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Expone actor/IP/request-id a signals de auditoría durante este request.
    "config.request_context.SecurityRequestContextMiddleware",
    # django-otp debe ir DESPUÉS de AuthenticationMiddleware.
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    # auditlog: capture el usuario que hace cada cambio en los modelos rastreados.
    "auditlog.middleware.AuditlogMiddleware",
    "csp.middleware.CSPMiddleware",
    "config.security_headers.SecurityHeadersMiddleware",  # Permissions-Policy
    # AxesMiddleware debe ir al final, después del de auth.
    "axes.middleware.AxesMiddleware",
]

# ---- Auth backends -------------------------------------------------------
# AxesStandaloneBackend va PRIMERO para que pueda bloquear antes de validar.
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
                "catalog.context_processors.site_context",
                "config.i18n_country.country_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.parse(
        secret_config(
            "DATABASE_URL",
            default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        ),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Custom user with roles (cliente / distribuidor / admin)
AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "catalog:home"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Localization: Peru por default (multi-país habilitado).
LANGUAGE_CODE = "es"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True

# Idiomas soportados. El switcher del header expone exactamente estos.
LANGUAGES = [
    ("es", "Español"),
    ("en", "English"),
    ("pt", "Português"),
]
# Carpeta donde viven los .po/.mo de las traducciones.
LOCALE_PATHS = [BASE_DIR / "locale"]

# Currency (default cuando no se conoce el país del visitante).
DEFAULT_CURRENCY = "USD"
DEFAULT_CURRENCY_SYMBOL = "$"

# Países soportados. Cada uno define su moneda, su flag emoji y su locale
# preferido. El selector se renderiza en el footer; las páginas pueden
# resolver `request.country` (vía middleware liviano) para decidir cosas
# como el método de pago default o el formato de número telefónico.
COUNTRIES = [
    {"code": "PE", "name": "Perú", "flag": "🇵🇪", "currency": "PEN", "symbol": "S/", "locale": "es", "phone_cc": "+51"},
    {"code": "CO", "name": "Colombia", "flag": "🇨🇴", "currency": "COP", "symbol": "$", "locale": "es", "phone_cc": "+57"},
    {"code": "MX", "name": "México", "flag": "🇲🇽", "currency": "MXN", "symbol": "$", "locale": "es", "phone_cc": "+52"},
    {"code": "AR", "name": "Argentina", "flag": "🇦🇷", "currency": "ARS", "symbol": "$", "locale": "es", "phone_cc": "+54"},
    {"code": "CL", "name": "Chile", "flag": "🇨🇱", "currency": "CLP", "symbol": "$", "locale": "es", "phone_cc": "+56"},
    {"code": "EC", "name": "Ecuador", "flag": "🇪🇨", "currency": "USD", "symbol": "$", "locale": "es", "phone_cc": "+593"},
    {"code": "BO", "name": "Bolivia", "flag": "🇧🇴", "currency": "BOB", "symbol": "Bs.", "locale": "es", "phone_cc": "+591"},
    {"code": "BR", "name": "Brasil", "flag": "🇧🇷", "currency": "BRL", "symbol": "R$", "locale": "pt", "phone_cc": "+55"},
    {"code": "US", "name": "USA", "flag": "🇺🇸", "currency": "USD", "symbol": "$", "locale": "en", "phone_cc": "+1"},
]
DEFAULT_COUNTRY = "EC"

# Static & media
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Django ≥4.2 reemplaza STATICFILES_STORAGE por la dict STORAGES. En Django 5
# el legacy STATICFILES_STORAGE es ignorado silenciosamente cuando STORAGES no
# está definido (Django usa el default StaticFilesStorage sin manifiesto). Por
# eso definimos STORAGES explícitamente para activar Whitenoise + manifiesto +
# hashing de filenames (cache busting).
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
PRIVATE_MEDIA_ROOT = BASE_DIR / "private_media"

# Tamaño máximo de upload (multipart). Necesario para imágenes del chat
# (5 MB efectivo + overhead de form-data). nginx en producción acepta hasta 20M
# (`client_max_body_size 20M`). Default de Django es 2.5 MB, demasiado bajo.
DATA_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024  # 8 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024  # 8 MB

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Identidades de correo separadas por función.
SYSTEM_EMAIL_ACCOUNT = config(
    "SYSTEM_EMAIL_ACCOUNT", default="codigosjheliz@protonmail.com"
)
OUTBOUND_FROM_EMAIL = config("OUTBOUND_FROM_EMAIL", default="corp@jhelizstore.xyz")
EMAIL_BACKEND = config(
    "EMAIL_BACKEND", default="config.corporate_email_backend.CorporateSMTPEmailBackend"
)
DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL", default=f"Jheliz <{OUTBOUND_FROM_EMAIL}>"
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL
SUPPORT_ADMIN_EMAIL = config("SUPPORT_ADMIN_EMAIL", default="")

# SMTP (opcional, para enviar correos reales en prod).
# Muchos VPS bloquean SMTP saliente; si es tu caso, usá BrevoEmailBackend (HTTP).
EMAIL_HOST = config("EMAIL_HOST", default="proton-bridge.internal")
EMAIL_PORT = config("EMAIL_PORT", default=1025, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default=OUTBOUND_FROM_EMAIL)
EMAIL_HOST_PASSWORD = secret_config("EMAIL_HOST_PASSWORD", allow_empty=True)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=False, cast=bool)

# Brevo (ex-Sendinblue) — backend HTTP, ver orders.brevo_backend.
# Activar con: EMAIL_BACKEND=orders.brevo_backend.BrevoEmailBackend
BREVO_API_KEY = config("BREVO_API_KEY", default="")

# Password reset: token de 24h en lugar del default de 3 días.
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24

# Mercado Pago
MERCADOPAGO_ACCESS_TOKEN = config("MERCADOPAGO_ACCESS_TOKEN", default="")
MERCADOPAGO_PUBLIC_KEY = config("MERCADOPAGO_PUBLIC_KEY", default="")
MERCADOPAGO_WEBHOOK_SECRET = config("MERCADOPAGO_WEBHOOK_SECRET", default="")
# Permite ocultar Mercado Pago como método de pago del checkout sin tener
# que borrar credenciales (útil para mantener la herramienta de diagnóstico
# operativa mientras se decide habilitar/deshabilitar MP frente al cliente).
MERCADOPAGO_CHECKOUT_ENABLED = config("MERCADOPAGO_CHECKOUT_ENABLED", default=True, cast=bool)

# Evita depender de una API externa durante desarrollo y pruebas. En
# produccion queda habilitado por defecto y siempre conserva el TC manual como
# respaldo si Binance no responde.
BINANCE_RATE_LIVE_ENABLED = config(
    "BINANCE_RATE_LIVE_ENABLED", default=not DEBUG, cast=bool
)

# Web Push notifications (VAPID).
# Para generar el par de claves:
#   from py_vapid import Vapid
#   v = Vapid()
#   v.generate_keys()
#   v.save_key("vapid_private.pem")
#   v.save_public_key("vapid_public.pem")
#   v.public_key  # Base64URL — esto va en VAPID_PUBLIC_KEY (lo lee el browser)
# La privada va en VAPID_PRIVATE_KEY como PEM o como base64url de la EC raw.
VAPID_PUBLIC_KEY = config("VAPID_PUBLIC_KEY", default="")
VAPID_PRIVATE_KEY = config("VAPID_PRIVATE_KEY", default="")
VAPID_CLAIM_EMAIL = config(
    "VAPID_CLAIM_EMAIL",
    default="mailto:soporte@jheliztv.xyz",
)

# Contact
WHATSAPP_NUMBER = config("WHATSAPP_NUMBER", default="+593960546224")
TELEGRAM_USERNAME = config("TELEGRAM_USERNAME", default="")

# Telegram bot (opcional)
TELEGRAM_BOT_TOKEN = config("TELEGRAM_BOT_TOKEN", default="")
TELEGRAM_ADMIN_CHAT_ID = config("TELEGRAM_ADMIN_CHAT_ID", default="")
# Token secreto que viaja en el header del webhook de Telegram
# (X-Telegram-Bot-Api-Secret-Token). Si está vacío, el webhook se deshabilita.
TELEGRAM_WEBHOOK_SECRET = config("TELEGRAM_WEBHOOK_SECRET", default="")
# Canal público de avisos para distribuidores (ej. "@jhelizservicetv" o
# "-1003689345000"). Si está vacío, las publicaciones automáticas a
# distribuidores se desactivan.
TELEGRAM_CHANNEL_ID = config("TELEGRAM_CHANNEL_ID", default="")
# Canal público de avisos para clientes finales (ej. "@tucanal").
# Si está vacío, las publicaciones automáticas a cliente final se
# desactivan, pero las del canal distribuidor siguen funcionando.
TELEGRAM_CUSTOMER_CHANNEL_ID = config("TELEGRAM_CUSTOMER_CHANNEL_ID", default="")
# Si False (default), nunca se publica automáticamente al canal cuando se
# crea o activa un producto/cupón. La publicación queda 100% manual desde
# el admin (acción "📢 Publicar en Telegram" o botón en el change form).
# Esto da al admin control total sobre qué y cuándo se anuncia.
TELEGRAM_AUTO_PUBLISH = config("TELEGRAM_AUTO_PUBLISH", default=False, cast=bool)

# ---- Bot de códigos (Telegram) -------------------------------------------
# Bot SEPARADO del bot principal: los clientes piden el código de Netflix
# (acceso temporal / actualizar hogar) de las cuentas que el admin les
# asignó. Lee una casilla central (Gmail) por IMAP a la que se reenvían los
# correos de Netflix de cada cuenta. Ver app ``codes``.
TELEGRAM_CODES_BOT_TOKEN = secret_config("TELEGRAM_CODES_BOT_TOKEN")
JHELIZ_CONTROL_TELEGRAM_BOT_TOKEN = secret_config(
    "JHELIZ_CONTROL_TELEGRAM_BOT_TOKEN",
    allow_empty=True,
)
JHELIZ_CONTROL_TELEGRAM_BOT_USERNAME = config(
    "JHELIZ_CONTROL_TELEGRAM_BOT_USERNAME",
    default="JHELIZCONTROLTV_bot",
).lstrip("@")
JHELIZ_CONTROL_BASE_URL = config(
    "JHELIZ_CONTROL_BASE_URL",
    default="https://jheliztv.xyz",
).rstrip("/")
# Chat ID del admin del bot de códigos (recibe avisos de altas nuevas).
TELEGRAM_CODES_ADMIN_CHAT_ID = config("TELEGRAM_CODES_ADMIN_CHAT_ID", default="")
# IDs opcionales de custom emojis. El bot conserva los emojis normales cuando
# un valor está vacío o Telegram rechaza el ID configurado.
CODES_PREMIUM_EMOJI_KEY_ID = config("CODES_PREMIUM_EMOJI_KEY_ID", default="")
CODES_PREMIUM_EMOJI_TRAVEL_ID = config("CODES_PREMIUM_EMOJI_TRAVEL_ID", default="")
CODES_PREMIUM_EMOJI_HOME_ID = config("CODES_PREMIUM_EMOJI_HOME_ID", default="")
CODES_PREMIUM_EMOJI_LOCK_ID = config("CODES_PREMIUM_EMOJI_LOCK_ID", default="")
CODES_PREMIUM_EMOJI_TV_ID = config("CODES_PREMIUM_EMOJI_TV_ID", default="")
CODES_PREMIUM_EMOJI_MAIL_ID = config("CODES_PREMIUM_EMOJI_MAIL_ID", default="")
CODES_PREMIUM_EMOJI_SUCCESS_ID = config("CODES_PREMIUM_EMOJI_SUCCESS_ID", default="")
CODES_PREMIUM_EMOJI_WARNING_ID = config("CODES_PREMIUM_EMOJI_WARNING_ID", default="")
CODES_PREMIUM_EMOJI_SPARKLES_ID = config(
    "CODES_PREMIUM_EMOJI_SPARKLES_ID", default=""
)
CODES_PREMIUM_EMOJI_HELP_ID = config("CODES_PREMIUM_EMOJI_HELP_ID", default="")
CODES_PREMIUM_EMOJI_CLIENTS_ID = config("CODES_PREMIUM_EMOJI_CLIENTS_ID", default="")
CODES_PREMIUM_EMOJI_ACTIVATE_ID = config("CODES_PREMIUM_EMOJI_ACTIVATE_ID", default="")
CODES_PREMIUM_EMOJI_DEACTIVATE_ID = config(
    "CODES_PREMIUM_EMOJI_DEACTIVATE_ID", default=""
)
CODES_PREMIUM_EMOJI_ASSIGN_ID = config("CODES_PREMIUM_EMOJI_ASSIGN_ID", default="")
CODES_PREMIUM_EMOJI_REMOVE_ID = config("CODES_PREMIUM_EMOJI_REMOVE_ID", default="")
CODES_PREMIUM_EMOJI_ANNOUNCEMENT_ID = config(
    "CODES_PREMIUM_EMOJI_ANNOUNCEMENT_ID", default=""
)
CODES_PREMIUM_EMOJI_SEARCH_ID = config("CODES_PREMIUM_EMOJI_SEARCH_ID", default="")
CODES_PREMIUM_EMOJI_TV_LINK_ID = config(
    "CODES_PREMIUM_EMOJI_TV_LINK_ID", default=""
)
# Casilla corporativa que recibe los correos de Netflix mediante Proton Bridge.
CODES_IMAP_HOST = config("CODES_IMAP_HOST", default="proton-bridge.internal")
CODES_IMAP_PORT = config("CODES_IMAP_PORT", default=1143, cast=int)
CODES_IMAP_USER = config("CODES_IMAP_USER", default=SYSTEM_EMAIL_ACCOUNT)
CODES_IMAP_PASSWORD = secret_config("CODES_IMAP_PASSWORD")
CODES_IMAP_SECURITY = config("CODES_IMAP_SECURITY", default="STARTTLS")
CODES_IMAP_TLS_VERIFY = config("CODES_IMAP_TLS_VERIFY", default=False, cast=bool)
# Segunda casilla opcional; vacía en producción.
CODES_IMAP2_HOST = config("CODES_IMAP2_HOST", default="")
CODES_IMAP2_PORT = config("CODES_IMAP2_PORT", default=993, cast=int)
CODES_IMAP2_USER = config("CODES_IMAP2_USER", default="")
CODES_IMAP2_PASSWORD = secret_config("CODES_IMAP2_PASSWORD", allow_empty=True)
CODES_IMAP2_SECURITY = config("CODES_IMAP2_SECURITY", default="SSL")
CODES_IMAP2_TLS_VERIFY = config("CODES_IMAP2_TLS_VERIFY", default=True, cast=bool)
# Ventana (minutos) hacia atrás para considerar un correo de Netflix vigente.
CODES_LOOKBACK_MINUTES = config("CODES_LOOKBACK_MINUTES", default=30, cast=int)
# Máximo de pedidos de código por cliente por día (0 = sin límite).
CODES_DAILY_LIMIT = config("CODES_DAILY_LIMIT", default=20, cast=int)
# Los mensajes con códigos/enlaces se eliminan de Telegram tras este tiempo.
# 0 desactiva la eliminación automática.
CODES_SENSITIVE_MESSAGE_TTL_SECONDS = config(
    "CODES_SENSITIVE_MESSAGE_TTL_SECONDS", default=600, cast=int
)
# Intentos sobre cuentas ajenas antes de bloquear pedidos temporalmente.
CODES_FOREIGN_ATTEMPT_LIMIT = config(
    "CODES_FOREIGN_ATTEMPT_LIMIT", default=3, cast=int
)
CODES_SECURITY_BLOCK_SECONDS = config(
    "CODES_SECURITY_BLOCK_SECONDS", default=900, cast=int
)
# Banner (imagen) que el bot manda en el /start. Vacío = sin banner.
CODES_BOT_BANNER = config(
    "CODES_BOT_BANNER", default=str(BASE_DIR / "codes" / "assets" / "banner.png")
)

# Bot de Disney+ (app ``codes``, módulo ``disney_bot``). Bot SEPARADO con su
# propio token: los clientes piden SOLO el código de inicio de sesión de las
# cuentas de Disney+ que el admin les asignó. Lee la MISMA casilla central
# (CODES_IMAP_*) a la que se reenvían los correos de Disney+.
TELEGRAM_DISNEY_BOT_TOKEN = config("TELEGRAM_DISNEY_BOT_TOKEN", default="")
# Chat ID del admin del bot de Disney+ (por defecto, el mismo del bot de Netflix).
TELEGRAM_DISNEY_ADMIN_CHAT_ID = config(
    "TELEGRAM_DISNEY_ADMIN_CHAT_ID", default=TELEGRAM_CODES_ADMIN_CHAT_ID
)
# Cuántos correos recientes (más nuevos primero) escanea como máximo el lector
# IMAP. Evita recorrer toda la bandeja cuando hay muchos correos.
CODES_IMAP_MAX_SCAN = config("CODES_IMAP_MAX_SCAN", default=25, cast=int)
# Timeout (segundos) de la conexión IMAP para que nunca quede colgada.
CODES_IMAP_TIMEOUT = config("CODES_IMAP_TIMEOUT", default=20, cast=int)
# Anti-spam: segundos mínimos entre dos lecturas de Gmail del mismo cliente.
CODES_COOLDOWN_SECONDS = config("CODES_COOLDOWN_SECONDS", default=6, cast=int)
# Mini-caché: segundos que se reutiliza un código ya leído (toques repetidos).
CODES_RESULT_CACHE_SECONDS = config("CODES_RESULT_CACHE_SECONDS", default=45, cast=int)

# Discord bot (opcional)
# Bot que reemplaza a Telegram para el back-office: pedidos nuevos, Yape,
# pedidos de codigo, distribuidores, soporte. Telegram queda solo para el
# canal publico de anuncios (JhelizTV|Avisos).
DISCORD_BOT_TOKEN = config("DISCORD_BOT_TOKEN", default="")
# ID del servidor Discord (guild) — numero largo. Se obtiene en Discord con
# click derecho sobre el nombre del servidor → "Copiar ID del servidor"
# (requiere Modo desarrollador activado en Ajustes → Avanzado).
DISCORD_GUILD_ID = config("DISCORD_GUILD_ID", default="")
# IDs de canales (se autocompletan despues con la primera ejecucion del
# comando ``discord_setup``, pero se pueden override aca via .env si querés).
DISCORD_CHANNEL_PEDIDOS = config("DISCORD_CHANNEL_PEDIDOS", default="")
DISCORD_CHANNEL_YAPE = config("DISCORD_CHANNEL_YAPE", default="")
DISCORD_CHANNEL_CODIGOS = config("DISCORD_CHANNEL_CODIGOS", default="")
DISCORD_CHANNEL_ALERTAS = config("DISCORD_CHANNEL_ALERTAS", default="")
DISCORD_CHANNEL_ADMIN = config("DISCORD_CHANNEL_ADMIN", default="")
DISCORD_CHANNEL_DASHBOARD = config("DISCORD_CHANNEL_DASHBOARD", default="")
DISCORD_CHANNEL_INCIDENCIAS = config("DISCORD_CHANNEL_INCIDENCIAS", default="")
DISCORD_CHANNEL_LOGS = config("DISCORD_CHANNEL_LOGS", default="")
# IDs de usuarios Discord autorizados a usar botones de acción
# (separados por coma). Si está vacío, los botones se desactivan por
# seguridad.
DISCORD_ADMIN_USER_IDS = config("DISCORD_ADMIN_USER_IDS", default="")
# Public Key del bot (Discord Developer Portal → General Information).
# Necesaria solo si querés activar los slash commands (`/buscar`,
# `/pendientes`, `/entregar`, `/stock`) — Discord firma cada interacción
# con esta llave y nosotros la verificamos antes de procesarla.
DISCORD_PUBLIC_KEY = config("DISCORD_PUBLIC_KEY", default="")
# Application ID del bot (mismo que Client ID — número largo). Solo se
# usa para registrar los slash commands desde manage.py.
DISCORD_APPLICATION_ID = config("DISCORD_APPLICATION_ID", default="")

# Brand
SITE_NAME = "JhelizTV"
SITE_TAGLINE = "Netflix, Disney+ y Office en Ecuador"

def _hashed_static(path: str) -> str:
    """Devuelve la URL de un static asset con hash de manifiesto si existe.

    Equivalente a `{% static path %}` en templates. Lo usamos en los lambdas
    de Unfold STYLES/SCRIPTS para que cada deploy con cambios en el CSS/JS
    custom genere una URL nueva (ej. `admin/jheliz_polish.abc123.css`),
    obligando a los browsers a refetchear y bypassear su cache de 1 año.
    """
    from django.contrib.staticfiles.storage import staticfiles_storage

    return staticfiles_storage.url(path)


# Unfold admin theme
UNFOLD = {
    "SITE_TITLE": "JhelizTV Admin",
    "SITE_HEADER": "JhelizTV",
    "SITE_SUBHEADER": "Panel de administración",
    "SITE_SYMBOL": "storefront",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "THEME": "dark",
    "BORDER_RADIUS": "12px",
    # Cargamos los assets custom vía staticfiles_storage.url() para que
    # CompressedManifestStaticFilesStorage le añada el hash de contenido al
    # filename (ej. /static/admin/jheliz_polish.abc123.css). Sin el hash, los
    # browsers cachean cada archivo 1 año (max-age=31536000 que setea whitenoise)
    # y los usuarios nunca reciben fixes de CSS/JS. Con el hash, cada deploy
    # con cambios genera una URL nueva que el browser refetchea sí o sí.
    "STYLES": [
        lambda request: _hashed_static("admin/jheliz_polish.css"),
        lambda request: _hashed_static("admin/notifications_bell.css"),
        lambda request: _hashed_static("admin/users_redesign.css"),
        lambda request: _hashed_static("admin/changelist_polish.css"),
        # Capa "2026": sistema de diseño moderno (glass cards, pills, bento
        # stats, empty states ilustrados). Se carga al final para que sus
        # tokens y clases `.jh2-*` puedan sobrescribir reglas previas.
        lambda request: _hashed_static("admin/jheliz_2026.css"),
        # Capa de tipografía 2026: Geist + Space Grotesk + JetBrains Mono,
        # gradient en titulares, refresco de sidebar/headings. Va al final
        # de las STYLES porque sobreescribe reglas de jheliz_2026.css.
        lambda request: _hashed_static("admin/typography_2026.css"),
        # Split-pane del chat en vivo (lista a la izquierda + conversación
        # a la derecha estilo Gmail/WhatsApp Web). Usa los tokens de fuente
        # de typography_2026.css, así que va después de esa.
        lambda request: _hashed_static("admin/livechat_splitpane.css"),
    ],
    "SCRIPTS": [
        lambda request: _hashed_static("admin/global_search.js"),
        lambda request: _hashed_static("admin/empty_state.js"),
        lambda request: _hashed_static("admin/ticket_templates.js"),
        lambda request: _hashed_static("admin/fab.js"),
        lambda request: _hashed_static("admin/toasts.js"),
        lambda request: _hashed_static("admin/keyboard_shortcuts.js"),
        lambda request: _hashed_static("admin/notifications_bell.js"),
        # PWA: inyecta <link rel="manifest"> + theme-color, registra el service
        # worker dedicado (/panel-jheliz-control/sw.js) y muestra un banner
        # "Instalar app" para que el admin se pueda guardar en el cel como
        # app independiente.
        lambda request: _hashed_static("admin/pwa_install.js"),
    ],
    "COLORS": {
        "primary": {
            "50": "239 246 255",
            "100": "219 234 254",
            "200": "191 219 254",
            "300": "147 197 253",
            "400": "96 165 250",
            "500": "59 130 246",
            "600": "37 99 235",
            "700": "29 78 216",
            "800": "30 64 175",
            "900": "30 58 138",
            "950": "23 37 84",
        },
    },
    "DASHBOARD_CALLBACK": "config.admin_dashboard.dashboard_callback",
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        # Reagrupada por WORKFLOW del día a día (no por modelo Django).
        # Orden basado en frecuencia de uso real:
        # Inicio → Vender (catálogo) → Pedidos → Clientes → Marketing → Soporte → Sistema.
        "navigation": [
            {
                "title": "✨ Inicio",
                "separator": False,
                "items": [
                    {
                        "title": "Dashboard",
                        "icon": "dashboard",
                        "link": "/panel-jheliz-control/",
                    },
                    {
                        "title": "Reportes financieros",
                        "icon": "monitoring",
                        "link": "/panel-jheliz-control/reports/",
                    },
                    {
                        "title": "Renovaciones",
                        "icon": "autorenew",
                        "link": "/panel-jheliz-control/renewals/",
                    },
                    {
                        "title": "Estado de servicios",
                        "icon": "health_and_safety",
                        "link": "/panel-jheliz-control/health/",
                    },
                    {
                        "title": "Ver tienda",
                        "icon": "public",
                        "link": "/",
                    },
                ],
            },
            {
                "title": "🛍️ Vender",
                "separator": True,
                "items": [
                    {
                        "title": "Productos",
                        "icon": "inventory_2",
                        "link": "/panel-jheliz-control/catalog/product/",
                    },
                    {
                        "title": "Planes — Cliente final",
                        "icon": "sell",
                        "link": "/panel-jheliz-control/catalog/customerplan/",
                    },
                    {
                        "title": "Planes — Distribuidor",
                        "icon": "storefront",
                        "link": "/panel-jheliz-control/catalog/distributorplan/",
                    },
                    {
                        "title": "Categorías",
                        "icon": "category",
                        "link": "/panel-jheliz-control/catalog/category/",
                    },
                    {
                        "title": "Stock por producto",
                        "icon": "inventory",
                        "link": "/panel-jheliz-control/stock/",
                    },
                    {
                        "title": "Stock (todos)",
                        "icon": "list_alt",
                        "link": "/panel-jheliz-control/catalog/stockitem/",
                    },
                    {
                        "title": "Avísame cuando vuelva",
                        "icon": "notifications_active",
                        "link": "/panel-jheliz-control/catalog/backinstockalert/",
                    },
                ],
            },
            {
                "title": "🧾 Pedidos",
                "separator": True,
                "items": [
                    {
                        "title": "Pedidos clientes",
                        "icon": "receipt_long",
                        "link": "/panel-jheliz-control/orders/order/",
                    },
                    {
                        "title": "Bandeja de pagos",
                        "icon": "qr_code_scanner",
                        "link": "/panel-jheliz-control/orders/order/yape-inbox/",
                    },
                    {
                        "title": "Items de pedidos",
                        "icon": "list_alt",
                        "link": "/panel-jheliz-control/orders/orderitem/",
                    },
                    {
                        "title": "Pedidos mayoristas",
                        "icon": "local_shipping",
                        "link": "/panel-jheliz-control/orders/distributororder/",
                    },
                    {
                        "title": "Reemplazar cuenta",
                        "icon": "sync_alt",
                        "link": "/panel-jheliz-control/replace-blocked-account/",
                    },
                ],
            },
            {
                "title": "🤝 Clientes",
                "separator": True,
                "items": [
                    {
                        "title": "Clientes",
                        "icon": "person",
                        "link": "/panel-jheliz-control/accounts/customer/",
                    },
                    {
                        "title": "Clientes 360°",
                        "icon": "groups",
                        "link": "/panel-jheliz-control/customers/",
                    },
                    {
                        "title": "Clientes valiosos",
                        "icon": "workspace_premium",
                        "link": "/panel-jheliz-control/top-customers/",
                    },
                    {
                        "title": "Distribuidores",
                        "icon": "badge",
                        "link": "/panel-jheliz-control/accounts/distributor/",
                    },
                    {
                        "title": "Movimientos de wallet",
                        "icon": "account_balance_wallet",
                        "link": "/panel-jheliz-control/accounts/wallettransaction/",
                    },
                ],
            },
            {
                "title": "🚀 Marketing",
                "separator": True,
                "items": [
                    {
                        "title": "Cupones / códigos",
                        "icon": "redeem",
                        "link": "/panel-jheliz-control/orders/coupon/",
                    },
                    {
                        "title": "Reseñas",
                        "icon": "reviews",
                        "link": "/panel-jheliz-control/catalog/testimonial/",
                    },
                    {
                        "title": "Posts del blog",
                        "icon": "article",
                        "link": "/panel-jheliz-control/blog/blogpost/",
                    },
                    {
                        "title": "Categorías de blog",
                        "icon": "label",
                        "link": "/panel-jheliz-control/blog/blogcategory/",
                    },
                ],
            },
            {
                "title": "🎧 Soporte",
                "separator": True,
                "items": [
                    {
                        "title": "Chats en vivo",
                        "icon": "chat",
                        "link": "/panel-jheliz-control/livechat/",
                    },
                    {
                        "title": "Tickets",
                        "icon": "support_agent",
                        "link": "/panel-jheliz-control/support/ticket/",
                    },
                    {
                        "title": "Solicitudes de código",
                        "icon": "mark_email_unread",
                        "link": "/panel-jheliz-control/support/coderequest/",
                    },
                ],
            },
            {
                "title": "🛠️ Sistema",
                "separator": True,
                "items": [
                    {
                        "title": "Config. de pagos",
                        "icon": "qr_code_2",
                        "link": "/panel-jheliz-control/orders/paymentsettings/",
                    },
                    {
                        "title": "Usuarios (staff)",
                        "icon": "group",
                        "link": "/panel-jheliz-control/accounts/user/",
                    },
                    {
                        "title": "2FA / autenticador",
                        "icon": "shield_lock",
                        "link": "/panel-jheliz-control/security/2fa/",
                    },
                    {
                        "title": "Auditoría",
                        "icon": "fact_check",
                        "link": "/panel-jheliz-control/auditoria/",
                    },
                ],
            },
        ],
    },
}

# ---------------------------------------------------------------------------
# Cifrado de datos sensibles en reposo
#
# Se usa para EncryptedTextField en orders.models.OrderItem.delivered_credentials.
# Generar con:  python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
# Si no se configura en DEBUG, se deriva de SECRET_KEY (sólo dev).
# ---------------------------------------------------------------------------
FIELD_ENCRYPTION_KEY = secret_config("FIELD_ENCRYPTION_KEY")
META_APP_ID = secret_config("META_APP_ID")
META_APP_SECRET = secret_config("META_APP_SECRET")
META_CONFIG_ID = secret_config("META_CONFIG_ID")
META_WEBHOOK_VERIFY_TOKEN = secret_config("META_WEBHOOK_VERIFY_TOKEN")
META_GRAPH_API_VERSION = config("META_GRAPH_API_VERSION", default="v23.0")

# ---------------------------------------------------------------------------
# django-axes: bloqueo por intentos fallidos de login
# ---------------------------------------------------------------------------
#
# Diez intentos por usuario+IP y una hora de enfriamiento frenan fuerza bruta
# sin bloquear a todos los clientes que comparten una IP de operador/NAT.
AXES_FAILURE_LIMIT = config("AXES_FAILURE_LIMIT", default=10, cast=int)
AXES_COOLOFF_TIME = config(
    # Acepta horas en decimales (0.5 = 30 min).
    "AXES_COOLOFF_TIME_HOURS", default=1.0, cast=float,
)
# Lockout sólo por (ip, username): un atacante que prueba varias contraseñas
# del mismo usuario es lo único que queremos frenar. Así NO bloqueamos a
# clientes detrás del mismo NAT/ISP cuando alguien más se equivoca.
AXES_LOCKOUT_PARAMETERS = [["ip_address", "username"]]
AXES_LOCKOUT_TEMPLATE = None  # usa el formulario default con mensaje de error
AXES_VERBOSE = False
# Cuando un cliente "se desloguea" tras un login exitoso, NO debe quedar con
# contador residual de intentos fallidos.
AXES_RESET_ON_SUCCESS = True
# Axes y nuestras alertas deben resolver exactamente la misma IP.
AXES_CLIENT_IP_CALLABLE = "config.client_ip.axes_client_ip"

# Sólo estos proxies pueden aportar X-Real-IP. El servicio web no está publicado
# externamente (Docker lo enlaza a 127.0.0.1), por lo que estas redes son internas.
TRUSTED_PROXY_NETWORKS = config(
    "TRUSTED_PROXY_NETWORKS",
    default="127.0.0.0/8,::1/128,172.16.0.0/12",
    cast=Csv(),
)

# Notificaciones (email + Telegram) cuando alguien inicia sesión en el admin.
# Útil para detectar rápido un acceso indebido — si recibes un correo de
# login y no fuiste tú, sabés que tu password se filtró.
ADMIN_LOGIN_NOTIFY = config("ADMIN_LOGIN_NOTIFY", default=True, cast=bool)
SECURITY_EVENT_ALERTS = config("SECURITY_EVENT_ALERTS", default=True, cast=bool)

# Logs estructurados y centralizables. Los SecurityEvent críticos también quedan
# persistidos en PostgreSQL aunque el contenedor sea recreado.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "security": {"format": "%(asctime)s level=%(levelname)s logger=%(name)s message=%(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "security"},
    },
    "loggers": {
        "security": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "axes": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

# ---------------------------------------------------------------------------
# 2FA (django-otp)
#
# El stack queda instalado pero el ENFORCEMENT (rechazar logins sin TOTP)
# se activa con ADMIN_2FA_ENFORCED=True una vez que tengas tu dispositivo
# TOTP registrado. Pasos (después de desplegar este PR):
#   1) Entra al admin con tu superuser actual.
#   2) Sección "TOTP devices" → "Añadir TOTP device" y escanea el QR con
#      Google Authenticator / Authy / 1Password.
#   3) Verifica que puedes usar el código (genera otro y entra de nuevo).
#   4) En tu .env de producción pon: ADMIN_2FA_ENFORCED=True
#      Esto fuerza que TODO superuser use TOTP. Si pierdes acceso, usa
#      `python manage.py addstatictoken <usuario>` para emitir un token
#      temporal de rescate por SSH.
# ---------------------------------------------------------------------------
ADMIN_2FA_ENFORCED = config("ADMIN_2FA_ENFORCED", default=False, cast=bool)
OTP_TOTP_ISSUER = "JhelizTV Admin"

# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Content Security Policy. Bloquea scripts/estilos/imágenes de orígenes
# que no estén en self. 'unsafe-inline' se mantiene en script/style por
# compatibilidad con el admin de Django/Unfold y con los bloques inline de
# las plantillas. 'unsafe-eval' es necesario para Alpine.js (lo usa Unfold
# para renderizar el sidebar, modales, etc. evaluando expresiones x-data,
# x-show, x-on con el constructor Function()).
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ("'self'",),
        # 'unsafe-eval' lo necesita Alpine.js (Unfold).
        # cdn.tailwindcss.com y unpkg.com los usa la tienda pública para Tailwind+htmx.
        "script-src": (
            "'self'",
            "'unsafe-inline'",
            "'unsafe-eval'",
            "https://cdn.tailwindcss.com",
            "https://unpkg.com",
        ),
        "style-src": (
            "'self'",
            "'unsafe-inline'",
            "https://fonts.googleapis.com",
        ),
        "font-src": ("'self'", "data:", "https://fonts.gstatic.com"),
        "img-src": ("'self'", "data:", "https:"),
        # Tailwind CDN hace fetch de su CSS dinámicamente; htmx hace requests al backend.
        "connect-src": ("'self'", "https://cdn.tailwindcss.com"),
        "frame-ancestors": ("'none'",),
        "base-uri": ("'self'",),
        "form-action": ("'self'",),
        "object-src": ("'none'",),
        "upgrade-insecure-requests": (),
    },
}

# Permissions-Policy (cabecera moderna que reemplaza a Feature-Policy).
# Bloqueamos APIs sensibles que el admin no necesita. Sólo incluimos
# features actualmente soportadas por Chromium para evitar warnings.
PERMISSIONS_POLICY = (
    "accelerometer=(), autoplay=(), camera=(), display-capture=(), "
    "encrypted-media=(), fullscreen=(self), geolocation=(), gyroscope=(), "
    "keyboard-map=(), magnetometer=(), microphone=(), midi=(), "
    "payment=(), picture-in-picture=(), publickey-credentials-get=(), "
    "screen-wake-lock=(), sync-xhr=(), usb=(), xr-spatial-tracking=()"
)

# ---------------------------------------------------------------------------
# Security in prod
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# Sesión persistente: por default Django deja la cookie de sesión SIN Max-Age,
# así que muchos navegadores/webviews de celular (los que abren el link desde
# WhatsApp/Telegram) la borran al cambiar de página o al cerrar, y al usuario
# "se le cierra la sesión al toque". Le damos 30 días de vida y la renovamos
# en cada request (expiración deslizante), de modo que mientras usen la app no
# los saca.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30  # 30 días
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = True

# Cookie de idioma (`django_language`): por default Django la setea como
# session cookie (sin Max-Age), lo que hace que se pierda cuando el
# usuario cierra el navegador o cuando un webview agresivo limpia
# session cookies entre páginas. Forzamos 1 año para que la elección
# manual del usuario persista.
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365  # 1 año
LANGUAGE_COOKIE_SAMESITE = "Lax"

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    LANGUAGE_COOKIE_SECURE = True
    # HSTS: 1 año + preload (cumple requisitos de hstspreload.org).
    # Sólo activa preload una vez que estés 100% seguro de que TODOS los
    # subdominios sirven HTTPS. Sacar HSTS preload requiere meses de espera.
    SECURE_HSTS_SECONDS = config(
        "SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 365, cast=int
    )
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = config("SECURE_HSTS_PRELOAD", default=True, cast=bool)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
