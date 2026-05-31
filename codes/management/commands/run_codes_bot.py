from django.core.management.base import BaseCommand

from codes import bot


class Command(BaseCommand):
    help = "Arranca el bot de códigos de Telegram por long polling."

    def handle(self, *args, **options):
        if not bot.is_configured():
            self.stderr.write(
                self.style.ERROR(
                    "TELEGRAM_CODES_BOT_TOKEN no configurado en .env. "
                    "Crea el bot con @BotFather y copia el token."
                )
            )
            return
        self.stdout.write(self.style.SUCCESS("Bot de códigos arrancando…"))
        bot.run_polling()
