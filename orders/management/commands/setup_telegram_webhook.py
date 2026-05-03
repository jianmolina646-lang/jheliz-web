"""Registra (o elimina) el webhook de Telegram contra la URL pública.

Uso:
    python manage.py setup_telegram_webhook
    python manage.py setup_telegram_webhook --info
    python manage.py setup_telegram_webhook --delete
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from orders import telegram


class Command(BaseCommand):
    help = "Registra el webhook de Telegram apuntando a este servidor."

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-url",
            default="https://jhelizservicestv.xyz",
            help="URL pública del sitio (https obligatorio para Telegram).",
        )
        parser.add_argument("--delete", action="store_true", help="Borra el webhook actual.")
        parser.add_argument("--info", action="store_true", help="Muestra el estado del webhook.")

    def handle(self, *args, base_url: str, delete: bool, info: bool, **opts):
        if not telegram.is_configured():
            raise CommandError("TELEGRAM_BOT_TOKEN no configurado en .env.")

        if info:
            self.stdout.write(str(telegram.get_webhook_info()))
            return
        if delete:
            self.stdout.write(str(telegram.delete_webhook()))
            return

        secret = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "") or ""
        if not secret:
            raise CommandError(
                "TELEGRAM_WEBHOOK_SECRET vacío. Define un valor aleatorio en .env "
                "(ej: `python -c 'import secrets;print(secrets.token_urlsafe(32))'`)."
            )
        url = f"{base_url.rstrip('/')}/pedidos/webhooks/telegram/{secret}/"
        result = telegram.set_webhook(url, secret_token=secret)
        if result.get("ok"):
            self.stdout.write(self.style.SUCCESS(f"Webhook registrado en {url}"))
        else:
            raise CommandError(f"Telegram rechazó el webhook: {result}")
