"""Registra los slash commands en Discord.

Uso:
    python manage.py discord_register_commands

Por defecto registra los comandos como "guild commands" (sólo visibles
dentro de tu servidor `Jheliz admin`). Esto los hace aparecer al
instante (los globales tardan hasta 1 hora). Si pasás --global, se
registran como comandos globales.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from discord_bot import client, interactions


class Command(BaseCommand):
    help = "Registra los slash commands del bot Jheliz en Discord."

    def add_arguments(self, parser):
        parser.add_argument(
            "--global", dest="globally", action="store_true",
            help="Registrar como comandos globales (tardan hasta 1h en propagarse).",
        )
        parser.add_argument(
            "--list", action="store_true",
            help="Sólo listar los comandos registrados, sin tocar nada.",
        )

    def handle(self, *args, globally: bool = False, list: bool = False, **options):
        token = getattr(settings, "DISCORD_BOT_TOKEN", "") or ""
        app_id = getattr(settings, "DISCORD_APPLICATION_ID", "") or ""
        guild_id = getattr(settings, "DISCORD_GUILD_ID", "") or ""

        if not token:
            raise CommandError("Falta DISCORD_BOT_TOKEN en el .env")
        if not app_id:
            raise CommandError("Falta DISCORD_APPLICATION_ID en el .env")
        if not globally and not guild_id:
            raise CommandError("Falta DISCORD_GUILD_ID; usá --global o configura el guild")

        if globally:
            url = f"/applications/{app_id}/commands"
            scope = "globales"
        else:
            url = f"/applications/{app_id}/guilds/{guild_id}/commands"
            scope = f"del guild {guild_id}"

        if list:
            existing = client._call("GET", url)
            if not existing:
                self.stdout.write(self.style.WARNING(f"Sin comandos {scope}."))
                return
            self.stdout.write(self.style.SUCCESS(
                f"{len(existing)} comando(s) {scope}:",
            ))
            for cmd in existing:
                self.stdout.write(f"  /{cmd['name']} — {cmd.get('description', '')}")
            return

        # Reemplazo completo via PUT (idempotente).
        payload = interactions.COMMAND_DEFINITIONS
        self.stdout.write(f"Registrando {len(payload)} comandos {scope}...")
        result = client._call("PUT", url, json=payload)
        if result is None:
            raise CommandError("Falló el registro. Revisá DISCORD_APPLICATION_ID y el token.")
        self.stdout.write(self.style.SUCCESS(
            f"✓ {len(result)} comando(s) registrados:",
        ))
        for cmd in result:
            self.stdout.write(f"  /{cmd['name']}")
        self.stdout.write("")
        self.stdout.write(
            "Acordate de configurar la \"Interactions Endpoint URL\" en "
            "Discord Developer Portal → General Information con:",
        )
        site = getattr(settings, "SITE_URL", "").rstrip("/") or "https://ecormecejhelizstore.com"
        self.stdout.write(self.style.SUCCESS(f"  {site}/discord/interactions/"))
