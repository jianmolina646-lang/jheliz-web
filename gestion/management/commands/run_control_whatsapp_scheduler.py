import time
import logging

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import close_old_connections, connections


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Ejecuta el envio de WhatsApp periodicamente con bajo consumo."

    def handle(self, *args, **options):
        while True:
            try:
                close_old_connections()
                call_command("send_control_whatsapp_reminders")
            except Exception:
                # Un fallo temporal de red o PostgreSQL no debe apagar para
                # siempre el programador de recordatorios.
                logger.exception("Falló el ciclo de recordatorios de WhatsApp")
                connections.close_all()
            time.sleep(900)
