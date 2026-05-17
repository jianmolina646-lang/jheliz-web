"""Crea (si faltan) los canales del back-office en Discord.

Crea una categoría "GESTIÓN" e dentro:
    - #pedidos-nuevos
    - #yape-pendientes
    - #codigos
    - #alertas
    - #admin (solo para mensajes internos del sistema)

Si los canales ya existen (por nombre exacto), los reutiliza. Imprime al
final el snippet `.env` con los IDs para que el usuario pueda pegarlo.

Uso:
    python manage.py discord_setup --guild 1505597453678674043
    python manage.py discord_setup           # usa DISCORD_GUILD_ID del .env
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from discord_bot import client


# Mapa: env-var → (canal a crear, descripción, key interna)
CHANNELS_TO_CREATE = [
    (
        "DISCORD_CHANNEL_PEDIDOS",
        "pedidos-nuevos",
        "Cada pedido nuevo de la web aparece acá con sus botones.",
    ),
    (
        "DISCORD_CHANNEL_YAPE",
        "yape-pendientes",
        "Comprobantes de Yape a confirmar o rechazar.",
    ),
    (
        "DISCORD_CHANNEL_CODIGOS",
        "codigos",
        "Pedidos del verificador de códigos. Botón 'Responder ahora' "
        "abre el admin.",
    ),
    (
        "DISCORD_CHANNEL_ALERTAS",
        "alertas",
        "Stock bajo, caídas, errores y otros avisos automáticos.",
    ),
    (
        "DISCORD_CHANNEL_ADMIN",
        "admin",
        "Solo admin — pruebas, debug y mensajes internos del bot.",
    ),
]

CATEGORY_NAME = "GESTIÓN"


class Command(BaseCommand):
    help = "Crea los canales del back-office en el servidor Discord."

    def add_arguments(self, parser):
        parser.add_argument(
            "--guild", default="",
            help="ID del servidor. Si se omite, usa DISCORD_GUILD_ID del .env.",
        )

    def handle(self, *args, **opts):
        if not client.is_configured():
            raise CommandError("DISCORD_BOT_TOKEN no configurado.")

        guild_id = (
            (opts.get("guild") or "").strip()
            or str(getattr(settings, "DISCORD_GUILD_ID", "") or "")
        )
        if not guild_id:
            raise CommandError(
                "Falta el ID del servidor. Pasalo con --guild o "
                "configura DISCORD_GUILD_ID en .env."
            )

        existing = client.list_channels(guild_id)
        if not existing:
            self.stderr.write(self.style.WARNING(
                "No pude listar canales. ¿Está el bot en el servidor y con "
                "permisos? Revisá invitándolo con permission=8 (admin)."
            ))

        # Indexa por (lowered_name, type).
        existing_by_name = {
            (c.get("name", "").lower(), c.get("type")): c for c in existing
        }

        # 1) Asegurar categoría.
        category = existing_by_name.get((CATEGORY_NAME.lower(), 4))
        if category:
            self.stdout.write(f"Categoría existente: {CATEGORY_NAME}")
        else:
            self.stdout.write(f"Creando categoría '{CATEGORY_NAME}'...")
            category = client.create_channel(
                guild_id, CATEGORY_NAME, channel_type=4,
            )
            if not category:
                raise CommandError(
                    "No pude crear la categoría. Revisá permisos del bot."
                )
        category_id = category.get("id")

        # 2) Asegurar canales de texto dentro de la categoría.
        out_env: list[str] = []
        for env_var, name, topic in CHANNELS_TO_CREATE:
            channel = existing_by_name.get((name.lower(), 0))
            if channel:
                self.stdout.write(f"  Canal #{name}: ya existe.")
            else:
                self.stdout.write(f"  Creando canal #{name}...")
                channel = client.create_channel(
                    guild_id, name, channel_type=0,
                    parent_id=category_id, topic=topic,
                )
                if not channel:
                    self.stderr.write(self.style.WARNING(
                        f"  No pude crear #{name}. Skipping."
                    ))
                    continue
            out_env.append(f"{env_var}={channel.get('id')}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Snippet para tu .env:"))
        self.stdout.write(f"DISCORD_GUILD_ID={guild_id}")
        for line in out_env:
            self.stdout.write(line)
