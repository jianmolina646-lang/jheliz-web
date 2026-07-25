from django.core.management.base import BaseCommand

from gestion.telegram_alerts import send_expiry_digests


class Command(BaseCommand):
    help = "Envía resúmenes Telegram de vencimientos por revendedor."

    def handle(self, *args, **options):
        total = send_expiry_digests()
        self.stdout.write(self.style.SUCCESS(f"Resúmenes Telegram enviados: {total}"))
