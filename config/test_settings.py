"""Settings used only by the automated test suite."""

from .settings import *  # noqa: F403


PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
BINANCE_RATE_LIVE_ENABLED = False

