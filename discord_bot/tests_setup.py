"""Tests para los management commands de setup y daily summary."""

from __future__ import annotations

from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings


@override_settings(
    DISCORD_BOT_TOKEN="fake",
    DISCORD_GUILD_ID="1234567890",
)
class DiscordSetupModernTests(TestCase):
    """``discord_setup`` debe ser idempotente y renombrar canales legacy."""

    def _run(self, mocked):
        from discord_bot.management.commands import discord_setup
        # Bypass the dataclass import path by patching the client module.
        with patch("discord_bot.management.commands.discord_setup.client") as cli:
            cli.is_configured.return_value = True
            for name, val in mocked.items():
                setattr(cli, name, val)
            out = StringIO()
            call_command("discord_setup", stdout=out, stderr=StringIO())
            return out.getvalue(), cli

    def test_creates_full_structure_on_empty_guild(self):
        # Guild vacío: ningún canal preexistente.
        from discord_bot.management.commands import discord_setup

        created_ids = iter([str(i) for i in range(1000, 1100)])

        def fake_create(guild_id, name, **kw):
            cid = next(created_ids)
            return {"id": cid, "name": name, "type": kw.get("channel_type", 0)}

        def fake_send_embed(cid, **kw):
            return {"id": f"msg-{cid}"}

        with patch.object(discord_setup, "client") as cli:
            cli.is_configured.return_value = True
            cli.list_channels.return_value = []
            cli.create_channel.side_effect = fake_create
            cli.edit_channel.return_value = None
            cli.send_embed.side_effect = fake_send_embed
            cli.list_pinned_messages.return_value = []
            cli.pin_message.return_value = True

            out = StringIO()
            call_command("discord_setup", stdout=out, stderr=StringIO())
            text = out.getvalue()

        # Se crearon 5 categorías + 8 canales.
        self.assertEqual(
            cli.create_channel.call_count,
            5 + 8,
            f"esperaba 13 creaciones, hubo {cli.create_channel.call_count}",
        )
        # Aparecen todos los env vars en el snippet
        for env_var in [
            "DISCORD_CHANNEL_PEDIDOS",
            "DISCORD_CHANNEL_YAPE",
            "DISCORD_CHANNEL_CODIGOS",
            "DISCORD_CHANNEL_ALERTAS",
            "DISCORD_CHANNEL_ADMIN",
            "DISCORD_CHANNEL_DASHBOARD",
            "DISCORD_CHANNEL_INCIDENCIAS",
            "DISCORD_CHANNEL_LOGS",
        ]:
            self.assertIn(env_var, text)
        # Se intentaron pinear bienvenidas (8 canales)
        self.assertEqual(cli.pin_message.call_count, 8)

    def test_renames_legacy_channels_without_recreating(self):
        from discord_bot.management.commands import discord_setup

        # Existen los canales viejos (sin emoji) + la categoría vieja "GESTIÓN".
        existing = [
            {"id": "9001", "name": "GESTIÓN", "type": 4, "parent_id": None},
            {"id": "9101", "name": "pedidos-nuevos", "type": 0, "parent_id": "9001", "topic": "viejo"},
            {"id": "9102", "name": "yape-pendientes", "type": 0, "parent_id": "9001", "topic": "viejo"},
            {"id": "9103", "name": "codigos", "type": 0, "parent_id": "9001", "topic": "viejo"},
            {"id": "9104", "name": "alertas", "type": 0, "parent_id": "9001", "topic": "viejo"},
            {"id": "9105", "name": "admin", "type": 0, "parent_id": "9001", "topic": "viejo"},
        ]
        created_ids = iter(["7001", "7002", "7003", "7004", "7005", "7006", "7007"])

        def fake_create(guild_id, name, **kw):
            return {"id": next(created_ids), "name": name, "type": kw.get("channel_type", 0)}

        with patch.object(discord_setup, "client") as cli:
            cli.is_configured.return_value = True
            cli.list_channels.return_value = existing
            cli.create_channel.side_effect = fake_create
            cli.edit_channel.return_value = None
            cli.send_embed.return_value = {"id": "msg-x"}
            cli.list_pinned_messages.return_value = []
            cli.pin_message.return_value = True

            out = StringIO()
            call_command("discord_setup", stdout=out, stderr=StringIO(), skip_welcome=True)

        # Los 5 canales legacy se renombran (no se crean nuevos).
        legacy_ids = {"9101", "9102", "9103", "9104", "9105"}
        edit_calls = cli.edit_channel.call_args_list
        renamed = {c.args[0] for c in edit_calls if c.args}
        self.assertTrue(legacy_ids.issubset(renamed))

        # Solo se crearon 3 canales nuevos (dashboard, incidencias, logs) +
        # 4 categorías nuevas (PAGOS, STOCK & ALERTAS, REPORTES, ADMIN).
        new_created = [c for c in cli.create_channel.call_args_list]
        # 4 categorías nuevas + 3 canales nuevos = 7 creates
        self.assertEqual(len(new_created), 7)

    def test_does_not_repin_welcome_if_already_pinned(self):
        """El comando es idempotente: no postea welcome dos veces."""
        from discord_bot.management.commands import discord_setup

        existing = [
            {"id": "1001", "name": "📥 GESTIÓN DE PEDIDOS", "type": 4, "parent_id": None},
            {"id": "1101", "name": "📥-pedidos-nuevos", "type": 0, "parent_id": "1001", "topic": "x"},
        ]

        with patch.object(discord_setup, "client") as cli:
            cli.is_configured.return_value = True
            cli.list_channels.return_value = existing
            cli.create_channel.return_value = {"id": "999", "name": "x", "type": 0}
            cli.edit_channel.return_value = None
            cli.send_embed.return_value = {"id": "y"}
            cli.pin_message.return_value = True
            # Devolver un pin previo del bot (con el marker)
            cli.list_pinned_messages.return_value = [
                {"embeds": [{"footer": {"text": "[Jheliz · setup] · algo"}}]},
            ]

            out = StringIO()
            call_command("discord_setup", stdout=out, stderr=StringIO())

        # Para pedidos-nuevos no se postea welcome (ya hay uno).
        # Los otros canales sí se crean y se postea welcome.
        # Verificamos que el send_embed se llamó menos que el total de canales (7 vs 8).
        self.assertLess(cli.send_embed.call_count, 8)

    def test_requires_token(self):
        from django.core.management import CommandError

        with patch("discord_bot.management.commands.discord_setup.client") as cli:
            cli.is_configured.return_value = False
            with self.assertRaises(CommandError):
                call_command("discord_setup", stdout=StringIO(), stderr=StringIO())


# --------------------------------------------------------------------------
# discord_daily_summary
# --------------------------------------------------------------------------

class DailySummaryTests(TestCase):
    def _make_order(self, *, status="delivered", currency="PEN", total="20.00"):
        from catalog.models import Category, Plan, Product
        from orders.models import Order, OrderItem
        cat, _ = Category.objects.get_or_create(name="C", defaults={"slug": "c"})
        product, _ = Product.objects.get_or_create(
            slug=f"ds-{status}-{currency}",
            defaults={"name": f"Prod {status}", "category": cat},
        )
        plan, _ = Plan.objects.get_or_create(
            product=product, name="1m",
            defaults={
                "duration_days": 30,
                "price_customer": Decimal(total),
                "price_distributor": Decimal("5.00"),
            },
        )
        order = Order.objects.create(
            email="x@example.com", currency=currency,
            total=Decimal(total), status=status,
            payment_provider="yape",
        )
        OrderItem.objects.create(
            order=order, product=product, plan=plan,
            product_name=product.name, plan_name=plan.name,
            unit_price=Decimal(total), quantity=1,
        )
        return order

    @override_settings(DISCORD_CHANNEL_DASHBOARD="42")
    def test_posts_summary_with_metrics(self):
        # Pedidos del día actual (days-back=0 captura "hoy")
        self._make_order(status="delivered", total="50.00")
        self._make_order(status="pending", total="20.00")

        with patch("discord_bot.client.send_embed") as send:
            send.return_value = {"id": "ok"}
            call_command(
                "discord_daily_summary",
                "--days-back", "0",
                stdout=StringIO(), stderr=StringIO(),
            )
            send.assert_called_once()
            _, kwargs = send.call_args
            self.assertIn("Resumen", kwargs["title"])
            # Hay fields con métricas
            fields_text = " ".join(f["value"] for f in kwargs["fields"])
            self.assertIn("2", fields_text)  # 2 pedidos del día

    @override_settings(DISCORD_CHANNEL_DASHBOARD="42")
    def test_dry_run_does_not_post(self):
        with patch("discord_bot.client.send_embed") as send:
            call_command(
                "discord_daily_summary",
                "--dry-run",
                stdout=StringIO(), stderr=StringIO(),
            )
            send.assert_not_called()

    @override_settings(DISCORD_CHANNEL_DASHBOARD="")
    def test_skips_when_channel_not_configured(self):
        with patch("discord_bot.client.send_embed") as send:
            call_command(
                "discord_daily_summary",
                stdout=StringIO(), stderr=StringIO(),
            )
            send.assert_not_called()


# --------------------------------------------------------------------------
# client.action_button helper
# --------------------------------------------------------------------------

class ActionButtonHelperTests(TestCase):
    def test_action_button_structure(self):
        from discord_bot import client

        btn = client.action_button("Hola", "x:y:1", emoji="✅")
        self.assertEqual(btn["type"], 2)
        self.assertEqual(btn["style"], client.BUTTON_SECONDARY)
        self.assertEqual(btn["label"], "Hola")
        self.assertEqual(btn["custom_id"], "x:y:1")
        self.assertEqual(btn["emoji"]["name"], "✅")
        self.assertNotIn("disabled", btn)

    def test_action_button_with_style_and_disabled(self):
        from discord_bot import client

        btn = client.action_button(
            "Borrar", "del:1",
            style=client.BUTTON_DANGER, disabled=True,
        )
        self.assertEqual(btn["style"], client.BUTTON_DANGER)
        self.assertTrue(btn["disabled"])
