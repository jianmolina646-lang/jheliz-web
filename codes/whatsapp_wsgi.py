"""Dedicated internal endpoint, hosted with the Telegram bot's configuration."""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
from django.conf import settings
settings.ROOT_URLCONF = 'codes.whatsapp_urls'
settings.SECURE_SSL_REDIRECT = False
settings.ALLOWED_HOSTS = ['codes-bridge', 'localhost', '127.0.0.1']
settings.WHATSAPP_CODES_BRIDGE_SECRET = os.environ.get('WHATSAPP_CODES_BRIDGE_SECRET', '')
settings.WHATSAPP_CODES_ADMIN_NUMBERS = os.environ.get('WHATSAPP_CODES_ADMIN_NUMBERS', '')
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
