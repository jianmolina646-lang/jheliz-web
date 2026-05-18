"""Crea o actualiza la estructura moderna del back-office en Discord.

Distribuye los canales en 5 categorías temáticas con emojis y descripciones,
y pinea en cada uno un embed de bienvenida que explica qué hace ese canal y
qué comandos son relevantes.

Es **idempotente**: si los canales ya existen (por el nombre actual o por
el nombre legacy sin emoji), los renombra y los reorganiza. Si el embed
de bienvenida ya está pinneado, no lo duplica.

Uso:

    python manage.py discord_setup
    python manage.py discord_setup --guild 1505597453678674043
    python manage.py discord_setup --skip-welcome   # solo estructura
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from discord_bot import client


WELCOME_MARKER = "[Jheliz · setup]"  # se incluye en cada welcome embed
                                     # para detectarlo y evitar duplicados.


@dataclass(frozen=True)
class ChannelSpec:
    env_var: str                # nombre de la var de entorno para el .env
    name: str                   # nombre actual (con emoji + slug)
    legacy_names: tuple[str, ...]  # nombres anteriores (para renombrar)
    topic: str                  # descripción del canal
    welcome_title: str
    welcome_description: str
    welcome_color: int


@dataclass(frozen=True)
class CategorySpec:
    name: str                   # nombre con emoji (ej. "📥 GESTIÓN DE PEDIDOS")
    legacy_names: tuple[str, ...]
    channels: tuple[ChannelSpec, ...]


# Paleta de colores semánticos (Discord modo oscuro)
COLOR_INFO = 0x6366F1
COLOR_SUCCESS = 0x22C55E
COLOR_WARNING = 0xF59E0B
COLOR_DANGER = 0xEF4444
COLOR_PURPLE = 0xA855F7


STRUCTURE: tuple[CategorySpec, ...] = (
    CategorySpec(
        name="📥 GESTIÓN DE PEDIDOS",
        legacy_names=("GESTIÓN", "gestion", "GESTION"),
        channels=(
            ChannelSpec(
                env_var="DISCORD_CHANNEL_PEDIDOS",
                name="📥-pedidos-nuevos",
                legacy_names=("pedidos-nuevos",),
                topic=(
                    "Cada pedido nuevo de la web aparece acá con su thread "
                    "propio. Click en el thread para ver el detalle y "
                    "marcarlo como entregado."
                ),
                welcome_title="📥 Pedidos nuevos",
                welcome_description=(
                    "**Acá llega cada pedido de la web** apenas se crea.\n\n"
                    "• Cada pedido abre **su propio thread** con embed completo "
                    "(producto, cliente, total, items, método de pago).\n"
                    "• Los **cambios de estado** (paid → preparing → delivered) "
                    "se postean adentro del thread.\n"
                    "• El thread **se archiva solo** cuando el pedido se entrega.\n\n"
                    "**Comandos útiles:**\n"
                    "`/buscar <email o JH-XXXX>` — ficha completa\n"
                    "`/entregar <JH-XXXX>` — abrir formulario de entrega\n"
                    "`/pendientes` — todo lo que falta atender"
                ),
                welcome_color=COLOR_INFO,
            ),
        ),
    ),
    CategorySpec(
        name="💰 PAGOS",
        legacy_names=(),
        channels=(
            ChannelSpec(
                env_var="DISCORD_CHANNEL_YAPE",
                name="💰-yape-pendientes",
                legacy_names=("yape-pendientes",),
                topic=(
                    "Comprobantes de Yape/Binance esperando confirmación. "
                    "Click 'Bandeja Yape' para verificar uno por uno."
                ),
                welcome_title="💰 Comprobantes pendientes",
                welcome_description=(
                    "**Cada comprobante de Yape o Binance** aparece acá con la "
                    "imagen + datos clave del pedido.\n\n"
                    "• **Botón \"Bandeja Yape\"** te lleva al admin para "
                    "confirmar o rechazar en lote.\n"
                    "• **Botón \"Ver pedido\"** abre el detalle completo.\n\n"
                    "**Comandos útiles:**\n"
                    "`/buscar JH-XXXX` — ver el pedido\n"
                    "`/pendientes` — todos los pagos a revisar"
                ),
                welcome_color=COLOR_WARNING,
            ),
            ChannelSpec(
                env_var="DISCORD_CHANNEL_CODIGOS",
                name="🔑-codigos",
                legacy_names=("codigos", "códigos"),
                topic=(
                    "Solicitudes del verificador `/codigos/`. Los clientes "
                    "te piden códigos de acceso (PIN, 2FA, recuperación)."
                ),
                welcome_title="🔑 Pedidos de código",
                welcome_description=(
                    "Cada vez que un cliente pide un código desde "
                    "`/codigos/` (recuperación, PIN, 2FA, etc.), aparece "
                    "acá con sus datos.\n\n"
                    "• **Botón \"Responder ahora\"** abre el admin con el "
                    "form listo para mandar la respuesta.\n"
                    "• Si el cliente eligió **\"Otro\"**, vas a ver la nota "
                    "explicativa que escribió."
                ),
                welcome_color=COLOR_PURPLE,
            ),
        ),
    ),
    CategorySpec(
        name="📦 STOCK & ALERTAS",
        legacy_names=(),
        channels=(
            ChannelSpec(
                env_var="DISCORD_CHANNEL_ALERTAS",
                name="🚨-alertas-stock",
                legacy_names=("alertas",),
                topic=(
                    "Stock bajo, caídas, errores y otros avisos automáticos."
                ),
                welcome_title="🚨 Alertas de stock",
                welcome_description=(
                    "Avisos automáticos cuando un plan se queda con poco "
                    "stock (por debajo del umbral configurado).\n\n"
                    "**Comandos útiles:**\n"
                    "`/stock <producto>` — ver stock disponible por plan\n"
                    "`/stock` — todos los planes con su semáforo "
                    "🟢/🔴"
                ),
                welcome_color=COLOR_DANGER,
            ),
            ChannelSpec(
                env_var="DISCORD_CHANNEL_INCIDENCIAS",
                name="⚠️-incidencias",
                legacy_names=("incidencias", "caidas"),
                topic=(
                    "Caídas de cuenta, devoluciones, reclamos y todo lo que "
                    "necesite atención manual."
                ),
                welcome_title="⚠️ Incidencias",
                welcome_description=(
                    "Espacio para registrar caídas de cuentas, "
                    "devoluciones, cambios urgentes y reclamos que "
                    "necesitan seguimiento manual.\n\n"
                    "Cuando integremos la detección automática de "
                    "caídas, los avisos van a postearse acá."
                ),
                welcome_color=COLOR_WARNING,
            ),
        ),
    ),
    CategorySpec(
        name="📊 REPORTES",
        legacy_names=(),
        channels=(
            ChannelSpec(
                env_var="DISCORD_CHANNEL_DASHBOARD",
                name="📊-dashboard",
                legacy_names=("dashboard",),
                topic=(
                    "Resumen diario de ventas y pedidos. Se postea "
                    "automáticamente cada día a las 9:00 AM."
                ),
                welcome_title="📊 Dashboard",
                welcome_description=(
                    "**Cada día a las 9:00 AM** se postea acá un resumen "
                    "automático del día anterior:\n\n"
                    "• Ventas totales (PEN + USD)\n"
                    "• Pedidos nuevos vs. entregados\n"
                    "• Top 3 productos más vendidos\n"
                    "• Pagos pendientes y por confirmar\n\n"
                    "**Comandos útiles:**\n"
                    "`/stats hoy` — métricas del día actual\n"
                    "`/stats semana` — comparativa semanal"
                ),
                welcome_color=COLOR_SUCCESS,
            ),
            ChannelSpec(
                env_var="DISCORD_CHANNEL_LOGS",
                name="📝-logs",
                legacy_names=("logs",),
                topic=(
                    "Auditoría de cambios importantes en el admin."
                ),
                welcome_title="📝 Logs",
                welcome_description=(
                    "Auditoría de cambios sensibles realizados en el admin "
                    "(usuarios, precios, configuración, etc.). Útil para "
                    "rastrear qué cambió y quién lo hizo."
                ),
                welcome_color=COLOR_INFO,
            ),
        ),
    ),
    CategorySpec(
        name="🔒 ADMIN",
        legacy_names=(),
        channels=(
            ChannelSpec(
                env_var="DISCORD_CHANNEL_ADMIN",
                name="🔒-admin",
                legacy_names=("admin",),
                topic=(
                    "Canal general del bot. Pruebas, debug, mensajes "
                    "internos del sistema y eventos sueltos."
                ),
                welcome_title="🔒 Admin",
                welcome_description=(
                    "Canal general del bot. Acá llegan:\n\n"
                    "• Mensajes de **prueba** del comando "
                    "`discord_test`\n"
                    "• Alertas de **login** sospechoso\n"
                    "• **Recargas de wallet** y eventos del sistema\n"
                    "• Cualquier `notify_admin` que no encaje en otro canal\n\n"
                    "**Comandos útiles desde acá:**\n"
                    "`/pendientes`, `/buscar`, `/stock`, `/stats`, `/cliente`"
                ),
                welcome_color=COLOR_PURPLE,
            ),
        ),
    ),
)


def _flatten_channels() -> list[ChannelSpec]:
    return [c for cat in STRUCTURE for c in cat.channels]


class Command(BaseCommand):
    help = (
        "Crea o actualiza la estructura moderna del back-office en Discord "
        "(categorías + canales con emoji + welcome embeds pinneados)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--guild", default="",
            help="ID del servidor. Si se omite, usa DISCORD_GUILD_ID del .env.",
        )
        parser.add_argument(
            "--skip-welcome", action="store_true",
            help="No postea/repin de welcome embeds (solo crea/renombra).",
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

        skip_welcome = opts.get("skip_welcome", False)

        existing = client.list_channels(guild_id)
        if not existing:
            self.stderr.write(self.style.WARNING(
                "No pude listar canales. ¿Está el bot en el servidor y con "
                "permisos? Revisá invitándolo con permission=8 (admin)."
            ))

        by_name: dict[tuple[str, int], dict] = {
            (c.get("name", "").lower(), c.get("type", 0)): c
            for c in existing
        }
        env_lines: list[str] = []

        for cat_spec in STRUCTURE:
            category = self._ensure_category(guild_id, cat_spec, by_name)
            if not category:
                continue
            category_id = category.get("id")

            for ch_spec in cat_spec.channels:
                channel = self._ensure_channel(
                    guild_id, ch_spec, category_id, by_name,
                )
                if not channel:
                    continue
                env_lines.append(f"{ch_spec.env_var}={channel.get('id')}")
                if not skip_welcome:
                    self._ensure_welcome_pin(channel.get("id"), ch_spec)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Snippet para tu .env:"))
        self.stdout.write(f"DISCORD_GUILD_ID={guild_id}")
        for line in env_lines:
            self.stdout.write(line)

    # ---------- categorías ----------

    def _ensure_category(self, guild_id, spec, by_name):
        # Probamos primero por el nombre actual; si no, por los legacy.
        for name in (spec.name, *spec.legacy_names):
            existing = by_name.get((name.lower(), 4))
            if existing:
                # Renombrar si quedó con el nombre viejo.
                if existing.get("name") != spec.name:
                    self.stdout.write(
                        f"Renombrando categoría '{existing.get('name')}' "
                        f"→ '{spec.name}'..."
                    )
                    client.edit_channel(existing["id"], name=spec.name)
                    existing["name"] = spec.name
                else:
                    self.stdout.write(f"Categoría OK: {spec.name}")
                return existing

        self.stdout.write(f"Creando categoría '{spec.name}'...")
        created = client.create_channel(
            guild_id, spec.name, channel_type=4,
        )
        if not created:
            self.stderr.write(self.style.WARNING(
                f"No pude crear la categoría '{spec.name}'. Skipping."
            ))
            return None
        by_name[(spec.name.lower(), 4)] = created
        return created

    # ---------- canales ----------

    def _ensure_channel(self, guild_id, spec, category_id, by_name):
        for name in (spec.name, *spec.legacy_names):
            existing = by_name.get((name.lower(), 0))
            if existing:
                patches = {}
                if existing.get("name") != spec.name:
                    patches["name"] = spec.name
                if (existing.get("topic") or "") != spec.topic:
                    patches["topic"] = spec.topic
                if str(existing.get("parent_id") or "") != str(category_id):
                    patches["parent_id"] = category_id
                if patches:
                    self.stdout.write(
                        f"  Actualizando #{existing.get('name')} "
                        f"→ #{spec.name}..."
                    )
                    updated = client.edit_channel(existing["id"], **patches)
                    if updated:
                        existing.update(updated)
                else:
                    self.stdout.write(f"  Canal OK: #{spec.name}")
                return existing

        self.stdout.write(f"  Creando canal #{spec.name}...")
        created = client.create_channel(
            guild_id, spec.name, channel_type=0,
            parent_id=category_id, topic=spec.topic,
        )
        if not created:
            self.stderr.write(self.style.WARNING(
                f"  No pude crear #{spec.name}. Skipping."
            ))
            return None
        by_name[(spec.name.lower(), 0)] = created
        return created

    # ---------- welcome embeds ----------

    def _ensure_welcome_pin(self, channel_id, spec):
        if not channel_id:
            return
        # No re-pineamos si ya hay un welcome del bot pinneado.
        already_pinned = False
        for msg in client.list_pinned_messages(channel_id):
            for emb in msg.get("embeds", []) or []:
                footer = ((emb.get("footer") or {}).get("text") or "")
                if WELCOME_MARKER in footer:
                    already_pinned = True
                    break
            if already_pinned:
                break
        if already_pinned:
            self.stdout.write(f"    Welcome embed ya pinneado en #{spec.name}.")
            return

        msg = client.send_embed(
            channel_id,
            title=spec.welcome_title,
            description=spec.welcome_description,
            color=spec.welcome_color,
            footer=f"{WELCOME_MARKER} · Tipeá `/` para ver todos los comandos",
        )
        if not msg:
            return
        client.pin_message(channel_id, msg.get("id"))
        self.stdout.write(f"    Welcome pinneado en #{spec.name}.")
