"""Production settings for the private distributor storefront."""

from .settings import *  # noqa: F403


ROOT_URLCONF = "config.urls"
SITE_URL = "https://marketingjhelizxyz.online"
SITE_NAME = "Jheliz Distribuidores"

ALLOWED_HOSTS = [
    "marketingjhelizxyz.online",
    "www.marketingjhelizxyz.online",
    "localhost",
    "127.0.0.1",
]
MARKETING_HOSTS = [
    "marketingjhelizxyz.online",
    "www.marketingjhelizxyz.online",
]
JHELIZTV_HOSTS = []
CSRF_TRUSTED_ORIGINS = [
    "https://marketingjhelizxyz.online",
    "https://www.marketingjhelizxyz.online",
]

DEFAULT_FROM_EMAIL = "Jheliz Distribuidores <no-reply@marketingjhelizxyz.online>"
SERVER_EMAIL = DEFAULT_FROM_EMAIL
OTP_TOTP_ISSUER = "Jheliz Distribuidores"
