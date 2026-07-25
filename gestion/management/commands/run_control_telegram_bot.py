from django.core.management.base import BaseCommand

from gestion.telegram_alerts import run_polling


class Command(BaseCommand):
    help = "Inicia el bot central de alertas de Jheliz Control."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Bot de alertas Jheliz Control iniciado."))
        run_polling()
