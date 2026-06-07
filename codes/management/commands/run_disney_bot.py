from django.core.management.base import BaseCommand

from codes import disney_bot


class Command(BaseCommand):
    help = "Arranca el bot de códigos de Disney+ de Telegram por long polling."

    def handle(self, *args, **options):
        if not disney_bot.is_configured():
            self.stderr.write(
                self.style.ERROR(
                    "TELEGRAM_DISNEY_BOT_TOKEN no configurado en .env. "
                    "Crea el bot con @BotFather y copia el token."
                )
            )
            return
        self.stdout.write(self.style.SUCCESS("Bot de Disney+ arrancando…"))
        disney_bot.run_polling()
