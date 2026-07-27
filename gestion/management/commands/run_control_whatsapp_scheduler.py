import time

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Ejecuta el envio de WhatsApp periodicamente con bajo consumo."

    def handle(self, *args, **options):
        while True:
            call_command("send_control_whatsapp_reminders")
            time.sleep(900)
