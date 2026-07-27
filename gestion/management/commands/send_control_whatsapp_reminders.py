from django.core.management.base import BaseCommand

from gestion.whatsapp import send_due_reminders


class Command(BaseCommand):
    help = "Envia recordatorios de vencimiento por WhatsApp Cloud API."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(f"Recordatorios enviados: {send_due_reminders()}"))
