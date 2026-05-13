"""Postea y fija un mensaje de bienvenida en cada canal público.

Pensado para correrse 1 vez (manualmente) cuando se acaba de armar los
canales. El mensaje queda fijado para que cualquier nuevo suscriptor lo
vea apenas entra. Si se vuelve a correr, postea otro mensaje y lo fija
encima del anterior (Telegram solo permite un mensaje fijado por canal).

Uso:
    python manage.py telegram_post_welcome
    python manage.py telegram_post_welcome --audience customer
    python manage.py telegram_post_welcome --audience distrib
    python manage.py telegram_post_welcome --no-pin
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from orders import telegram


_DIVIDER = "━━━━━━━━━━━━━━━━━━"


def _customer_welcome() -> str:
    return "\n".join([
        "🎬 <b>¡BIENVENIDO A JHELIZ!</b> 📺",
        "",
        _DIVIDER,
        "",
        "🌟 <b>Streaming premium al mejor precio en Perú</b>",
        "",
        "✨ <b>Lo que vas a encontrar acá:</b>",
        "",
        "     📺  Stock fresco diario (Netflix, Disney+, HBO, Crunchyroll, Spotify…)",
        "     💸  Ofertas y cupones exclusivos del canal",
        "     ⚡  Avisos cuando vuelve un servicio caído",
        "     🎁  Sorteos para suscriptores",
        "",
        _DIVIDER,
        "",
        '🛒  <b>Comprar:</b>  <a href="https://ecormecejhelizstore.com">ecormecejhelizstore.com</a>',
        "💬  <b>Soporte:</b>  @ecomercejheliz",
        "🤖  <b>Bot:</b>  @jhelizservicetvxyz_bot",
        "",
        _DIVIDER,
        "",
        "🏪 <i>¿Sos distribuidor mayorista?</i>",
        "Unite al canal exclusivo:  @jhelizservicetv",
        "",
        "¡Gracias por seguirnos! ❤️",
    ])


def _distrib_welcome() -> str:
    return "\n".join([
        "🏪 <b>JHELIZ · CANAL DE DISTRIBUIDORES</b>",
        "",
        _DIVIDER,
        "",
        "💼 <b>Stock mayorista exclusivo</b>",
        "",
        "🔥 <b>Lo que vas a encontrar acá:</b>",
        "",
        "     📦  Avisos inmediatos cuando llega stock nuevo",
        "     💰  Precios mayoristas (más bajos que el canal público)",
        "     ⚡  Reposición de cuentas caídas express",
        "     🎯  Lotes promocionales para revender",
        "",
        _DIVIDER,
        "",
        '🛒  <b>Comprar:</b>  <a href="https://ecormecejhelizstore.com">ecormecejhelizstore.com</a>',
        "💳  <b>Wallet:</b>  pagás con saldo prepago, entrega instantánea",
        "🤖  <b>Comandos del bot:</b>  /saldo  /pedido  /buscar",
        "💬  <b>Soporte directo:</b>  @ecomercejheliz",
        "",
        _DIVIDER,
        "",
        "⚠️ <i>Canal de acceso restringido — para mayoristas autorizados</i>",
        "📩 ¿Querés ser distribuidor? Escribí a @ecomercejheliz",
        "",
        "¡Gracias por trabajar con Jheliz! 🤝",
    ])


class Command(BaseCommand):
    help = (
        "Postea (y opcionalmente fija) un mensaje de bienvenida bonito en "
        "los canales públicos de Telegram. Pensado para correrlo una sola "
        "vez al armar los canales."
    )

    AUDIENCES = ("customer", "distrib", "both")

    def add_arguments(self, parser):
        parser.add_argument(
            "--audience",
            choices=self.AUDIENCES,
            default="both",
            help="Audiencia a la que postear (default: both).",
        )
        parser.add_argument(
            "--no-pin",
            action="store_true",
            help="No fijar el mensaje (solo postearlo).",
        )

    def handle(self, *args, audience: str, no_pin: bool, **opts):
        if not telegram.is_configured():
            raise CommandError("TELEGRAM_BOT_TOKEN no configurado.")

        targets: list[tuple[str, str, str]] = []
        if audience in ("customer", "both"):
            chat_id = telegram._customer_channel_id()
            if chat_id:
                targets.append((chat_id, "customer", _customer_welcome()))
            else:
                self.stdout.write(self.style.WARNING(
                    "TELEGRAM_CUSTOMER_CHANNEL_ID vacío — se omite canal customer.",
                ))
        if audience in ("distrib", "both"):
            chat_id = telegram._distrib_channel_id()
            if chat_id:
                targets.append((chat_id, "distrib", _distrib_welcome()))
            else:
                self.stdout.write(self.style.WARNING(
                    "TELEGRAM_CHANNEL_ID vacío — se omite canal distrib.",
                ))

        if not targets:
            raise CommandError("No hay canales configurados.")

        for chat_id, name, text in targets:
            self.stdout.write(f"📤 Posteando bienvenida en {name} ({chat_id})…")
            res = telegram.send_message(chat_id, text)
            if not res.get("ok"):
                self.stdout.write(self.style.ERROR(f"   ❌ Falló: {res}"))
                continue
            message_id = res["result"]["message_id"]
            self.stdout.write(self.style.SUCCESS(f"   ✓ Posteado (message_id={message_id})"))
            if no_pin:
                continue
            pin_res = telegram._call(
                "pinChatMessage",
                chat_id=chat_id,
                message_id=message_id,
                disable_notification=True,
            )
            if pin_res.get("ok"):
                self.stdout.write(self.style.SUCCESS("   📌 Fijado al tope del canal"))
            else:
                self.stdout.write(self.style.WARNING(
                    f"   ⚠ No se pudo fijar (necesita permiso 'pin messages'): {pin_res}",
                ))
