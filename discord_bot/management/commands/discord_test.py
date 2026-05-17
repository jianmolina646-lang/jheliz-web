"""Verifica la conexión con el bot de Discord.

Uso:
    python manage.py discord_test                     # solo lista identidad + servidores
    python manage.py discord_test --send admin        # manda un msg de prueba al canal "admin"
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from discord_bot import client, notifications


class Command(BaseCommand):
    help = "Verifica la conexión con Discord y opcionalmente manda un test."

    def add_arguments(self, parser):
        parser.add_argument(
            "--send",
            choices=["admin", "pedidos", "yape", "codigos", "alertas"],
            default=None,
            help="Si se indica, manda un mensaje de prueba a ese canal.",
        )

    def handle(self, *args, **opts):
        if not client.is_configured():
            self.stderr.write(self.style.ERROR(
                "DISCORD_BOT_TOKEN no está configurado en el entorno."
            ))
            return

        me = client.get_me()
        if not me:
            self.stderr.write(self.style.ERROR(
                "No pude autenticarme contra Discord. Revisá el token."
            ))
            return
        self.stdout.write(self.style.SUCCESS(
            f"Bot autenticado: {me.get('username')} (id={me.get('id')})"
        ))

        guilds = client.list_guilds()
        if not guilds:
            self.stdout.write(self.style.WARNING(
                "El bot no está en ningún servidor todavía. Invitalo con "
                "https://discord.com/api/oauth2/authorize?client_id="
                f"{me.get('id')}&permissions=8&scope=bot+applications.commands"
            ))
            return
        self.stdout.write("Servidores donde está el bot:")
        for g in guilds:
            self.stdout.write(f"  - {g.get('name')} (id={g.get('id')})")

        send_target = opts.get("send")
        if send_target:
            result = notifications.notify_test(
                channel_key=send_target,
                message=(
                    f"✅ Test de conexión Discord OK — "
                    f"bot **{me.get('username')}** respondiendo."
                ),
            )
            if result:
                self.stdout.write(self.style.SUCCESS(
                    f"Mensaje de prueba enviado al canal '{send_target}'."
                ))
            else:
                self.stderr.write(self.style.WARNING(
                    f"No pude mandar al canal '{send_target}'. "
                    "Quizás falta configurar DISCORD_CHANNEL_"
                    f"{send_target.upper()} en .env."
                ))
