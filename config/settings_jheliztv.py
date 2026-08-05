"""Production settings for the standalone JHELIZCONTROLTV deployment."""

from .settings import *  # noqa: F403


ROOT_URLCONF = "config.urls_jheliztv"
SITE_URL = "https://jheliztv.xyz"
SITE_NAME = "JHELIZCONTROLTV"

ALLOWED_HOSTS = ["jheliztv.xyz", "www.jheliztv.xyz", "localhost", "127.0.0.1"]
JHELIZTV_HOSTS = ["jheliztv.xyz", "www.jheliztv.xyz"]
CSRF_TRUSTED_ORIGINS = ["https://jheliztv.xyz", "https://www.jheliztv.xyz"]

DEFAULT_FROM_EMAIL = "JHELIZCONTROLTV <no-reply@jheliztv.xyz>"
SERVER_EMAIL = DEFAULT_FROM_EMAIL
SECURITY_EMAIL = "soporte@jheliztv.xyz"
OTP_TOTP_ISSUER = "JHELIZCONTROLTV"
