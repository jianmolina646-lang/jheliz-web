from django.core.management.base import BaseCommand

from orders import telegram


class Command(BaseCommand):
    help = "Arranca el bot de Telegram de Jheliz por long polling."

    def handle(self, *args, **options):
        if not telegram.is_configured():
            self.stderr.write(self.style.ERROR(
                "TELEGRAM_BOT_TOKEN no configurado en .env. Crea un bot con @BotFather y copia el token."
            ))
            return
        self.stdout.write(self.style.SUCCESS("Bot Jheliz arrancando…"))
        telegram.run_polling()
