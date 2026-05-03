"""Envía el resumen diario al chat admin (cron 8am Perú).

Uso:
    python manage.py telegram_daily_summary
"""

from django.core.management.base import BaseCommand

from orders import telegram


class Command(BaseCommand):
    help = "Envía el resumen diario al admin por Telegram."

    def handle(self, *args, **opts):
        if not telegram.is_configured():
            self.stdout.write("TELEGRAM_BOT_TOKEN no configurado. Saltando.")
            return
        text = telegram.daily_summary_text()
        result = telegram.notify_admin(text)
        if result and result.get("ok"):
            self.stdout.write(self.style.SUCCESS("Resumen enviado."))
        else:
            self.stdout.write(self.style.WARNING(f"Error: {result}"))
