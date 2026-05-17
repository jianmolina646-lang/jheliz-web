from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings

from discord_bot import client, notifications


# --------------------------------------------------------------------------
# Cliente HTTP
# --------------------------------------------------------------------------

class DiscordClientTests(TestCase):
    """Verifica que el cliente Discord nunca rompa la app si está apagado."""

    @override_settings(DISCORD_BOT_TOKEN="")
    def test_is_configured_false_without_token(self):
        self.assertFalse(client.is_configured())

    @override_settings(DISCORD_BOT_TOKEN="fake-token")
    def test_is_configured_true_with_token(self):
        self.assertTrue(client.is_configured())

    @override_settings(DISCORD_BOT_TOKEN="")
    def test_send_message_returns_none_without_token(self):
        self.assertIsNone(client.send_message("123", "hola"))

    @override_settings(DISCORD_BOT_TOKEN="fake-token")
    def test_send_message_handles_network_error(self):
        with patch("discord_bot.client.requests.request") as mock_req:
            import requests as r
            mock_req.side_effect = r.ConnectionError("offline")
            self.assertIsNone(client.send_message("123", "hola"))

    @override_settings(DISCORD_BOT_TOKEN="fake-token")
    def test_send_message_handles_4xx(self):
        with patch("discord_bot.client.requests.request") as mock_req:
            mock_req.return_value.status_code = 403
            mock_req.return_value.text = "Forbidden"
            self.assertIsNone(client.send_message("123", "hola"))

    @override_settings(DISCORD_BOT_TOKEN="fake-token")
    def test_send_message_returns_data_on_2xx(self):
        with patch("discord_bot.client.requests.request") as mock_req:
            mock_req.return_value.status_code = 200
            mock_req.return_value.content = b'{"id":"42"}'
            mock_req.return_value.json.return_value = {"id": "42"}
            result = client.send_message("123", "hola")
            self.assertEqual(result, {"id": "42"})

    def test_link_button_shape(self):
        btn = client.link_button("Abrir", "https://example.com", emoji="🔗")
        self.assertEqual(btn["type"], 2)
        self.assertEqual(btn["style"], 5)
        self.assertEqual(btn["label"], "Abrir")
        self.assertEqual(btn["url"], "https://example.com")
        self.assertEqual(btn["emoji"], {"name": "🔗"})

    def test_action_row_shape(self):
        row = client.action_row(
            client.link_button("A", "https://x/"),
            client.link_button("B", "https://y/"),
        )
        self.assertEqual(row["type"], 1)
        self.assertEqual(len(row["components"]), 2)

    @override_settings(DISCORD_BOT_TOKEN="fake-token")
    def test_start_thread_from_message(self):
        with patch("discord_bot.client.requests.request") as mock_req:
            mock_req.return_value.status_code = 200
            mock_req.return_value.content = b'{"id":"99"}'
            mock_req.return_value.json.return_value = {"id": "99"}
            thread = client.start_thread_from_message("ch1", "msg1", "JH-0001")
            self.assertEqual(thread, {"id": "99"})
            args, kwargs = mock_req.call_args
            self.assertEqual(args[0], "POST")
            self.assertIn("/channels/ch1/messages/msg1/threads", args[1])
            self.assertEqual(kwargs["json"]["name"], "JH-0001")


# --------------------------------------------------------------------------
# Pedidos de código
# --------------------------------------------------------------------------

class NotifyNewCodeRequestTests(TestCase):

    @override_settings(DISCORD_BOT_TOKEN="", DISCORD_CHANNEL_CODIGOS="")
    def test_no_op_when_token_missing(self):
        with patch("discord_bot.client.requests.request") as mock_req:
            from support.models import CodeRequest
            cr = CodeRequest.objects.create(
                platform=CodeRequest.Platform.NETFLIX,
                account_email="t@example.com",
                audience=CodeRequest.Audience.CUSTOMER,
            )
            result = notifications.notify_new_code_request(None, cr)
            self.assertIsNone(result)
            mock_req.assert_not_called()

    @override_settings(
        DISCORD_BOT_TOKEN="fake-token",
        DISCORD_CHANNEL_CODIGOS="9999",
        SITE_URL="https://test.local",
    )
    def test_posts_embed_with_relevant_fields(self):
        from support.models import CodeRequest
        cr = CodeRequest.objects.create(
            platform=CodeRequest.Platform.NETFLIX,
            account_email="t@example.com",
            audience=CodeRequest.Audience.CUSTOMER,
            requested_code_type="other",
            note="Estoy de viaje en Cusco y me pide código",
            order_number="JH-0042",
        )

        with patch("discord_bot.client.requests.request") as mock_req:
            mock_req.return_value.status_code = 200
            mock_req.return_value.content = b'{"id":"42"}'
            mock_req.return_value.json.return_value = {"id": "42"}

            notifications.notify_new_code_request(None, cr)

            self.assertEqual(mock_req.call_count, 1)
            args, kwargs = mock_req.call_args
            payload = kwargs["json"]
            embed = payload["embeds"][0]
            self.assertIn("Nuevo pedido de código", embed["title"])

            fields_text = " ".join(
                f"{f['name']}={f['value']}" for f in embed["fields"]
            )
            self.assertIn("Netflix", fields_text)
            self.assertIn("t@example.com", fields_text)
            self.assertIn("JH-0042", fields_text)
            self.assertIn("Cusco", fields_text)


# --------------------------------------------------------------------------
# Pedidos (flow completo)
# --------------------------------------------------------------------------

@override_settings(
    DISCORD_BOT_TOKEN="fake-token",
    DISCORD_CHANNEL_PEDIDOS="1001",
    DISCORD_CHANNEL_YAPE="1002",
    DISCORD_CHANNEL_ALERTAS="1003",
    SITE_URL="https://test.local",
    ADMIN_URL_PATH="panel-jheliz-2026",
)
class NotifyOrderTests(TestCase):

    def _make_order(self, *, status="pending"):
        from catalog.models import Category, Plan, Product
        from orders.models import Order, OrderItem
        cat, _ = Category.objects.get_or_create(
            name="Streaming", defaults={"slug": "streaming"},
        )
        product, _ = Product.objects.get_or_create(
            slug=f"np-{status}",
            defaults={"name": f"Netflix Premium {status}", "category": cat},
        )
        plan, _ = Plan.objects.get_or_create(
            product=product, name="1 mes",
            defaults={
                "duration_days": 30,
                "price_customer": Decimal("10.00"),
                "price_distributor": Decimal("8.00"),
            },
        )
        order = Order.objects.create(
            email="x@example.com", phone="+51999",
            currency="PEN", total=Decimal("10.00"),
            status=status, payment_provider="yape",
        )
        OrderItem.objects.create(
            order=order, product=product, plan=plan,
            product_name=product.name, plan_name=plan.name,
            unit_price=Decimal("10.00"), quantity=1,
        )
        return order

    def test_is_backoffice_configured(self):
        self.assertTrue(notifications.is_backoffice_configured())

    @override_settings(DISCORD_CHANNEL_PEDIDOS="")
    def test_is_backoffice_configured_false_without_pedidos_channel(self):
        self.assertFalse(notifications.is_backoffice_configured())

    def test_notify_new_order_creates_thread_and_db_row(self):
        order = self._make_order()
        responses = [
            # 1) send_embed -> retorna mensaje con id
            {"id": "msg1"},
            # 2) start_thread_from_message -> retorna thread con id
            {"id": "thread1"},
        ]
        call_iter = iter(responses)

        with patch("discord_bot.client.requests.request") as mock_req:
            def fake_request(method, url, **kwargs):
                resp = mock_req.return_value
                resp.status_code = 200
                resp.content = b'{"id":"x"}'
                resp.json.return_value = next(call_iter)
                return resp

            mock_req.side_effect = fake_request
            result = notifications.notify_new_order(order)

            self.assertIsNotNone(result)
            self.assertEqual(mock_req.call_count, 2)

            from discord_bot.models import DiscordOrderThread
            mapping = DiscordOrderThread.objects.get(order=order)
            self.assertEqual(mapping.thread_id, "thread1")
            self.assertEqual(mapping.root_message_id, "msg1")
            self.assertEqual(mapping.last_status_posted, "pending")

    def test_notify_new_order_is_idempotent(self):
        """Si ya hay thread, no duplica."""
        order = self._make_order()
        from discord_bot.models import DiscordOrderThread
        DiscordOrderThread.objects.create(
            order=order, channel_id="1001", thread_id="t",
            root_message_id="m", last_status_posted="pending",
        )
        with patch("discord_bot.client.requests.request") as mock_req:
            result = notifications.notify_new_order(order)
            self.assertIsNone(result)
            mock_req.assert_not_called()

    def test_notify_order_status_change_posts_in_thread(self):
        order = self._make_order(status="pending")
        from discord_bot.models import DiscordOrderThread
        DiscordOrderThread.objects.create(
            order=order, channel_id="1001", thread_id="t-42",
            last_status_posted="pending",
        )
        order.status = "paid"

        with patch("discord_bot.client.requests.request") as mock_req:
            mock_req.return_value.status_code = 200
            mock_req.return_value.content = b'{"id":"m"}'
            mock_req.return_value.json.return_value = {"id": "m"}

            notifications.notify_order_status_change(order, prev_status="pending")
            self.assertGreaterEqual(mock_req.call_count, 1)
            # El primer POST debería ir al thread, no al canal raíz.
            first_call = mock_req.call_args_list[0]
            self.assertIn("/channels/t-42/messages", first_call.args[1])

            # Last status updated.
            mapping = DiscordOrderThread.objects.get(order=order)
            self.assertEqual(mapping.last_status_posted, "paid")

    def test_notify_order_status_change_archives_on_terminal(self):
        order = self._make_order(status="paid")
        from discord_bot.models import DiscordOrderThread
        DiscordOrderThread.objects.create(
            order=order, channel_id="1001", thread_id="t-99",
            last_status_posted="paid",
        )
        order.status = "delivered"

        with patch("discord_bot.client.requests.request") as mock_req:
            mock_req.return_value.status_code = 200
            mock_req.return_value.content = b'{"id":"m"}'
            mock_req.return_value.json.return_value = {"id": "m"}

            notifications.notify_order_status_change(order, prev_status="paid")
            # Debería haber al menos 2 llamadas: post + archive PATCH.
            methods = [c.args[0] for c in mock_req.call_args_list]
            self.assertIn("PATCH", methods)

    def test_notify_yape_pending(self):
        order = self._make_order(status="verifying")
        with patch("discord_bot.client.requests.request") as mock_req:
            mock_req.return_value.status_code = 200
            mock_req.return_value.content = b'{"id":"y"}'
            mock_req.return_value.json.return_value = {"id": "y"}

            result = notifications.notify_yape_pending(order)
            self.assertIsNotNone(result)
            first_call = mock_req.call_args_list[0]
            self.assertIn("/channels/1002/messages", first_call.args[1])
            payload = first_call.kwargs["json"]
            embed = payload["embeds"][0]
            self.assertIn("Comprobante", embed["title"])

    def test_notify_stock_low(self):
        with patch("discord_bot.client.requests.request") as mock_req:
            mock_req.return_value.status_code = 200
            mock_req.return_value.content = b'{"id":"s"}'
            mock_req.return_value.json.return_value = {"id": "s"}

            notifications.notify_stock_low(
                product_name="Netflix Premium — 1 mes", total=1, threshold=3,
            )
            args, kwargs = mock_req.call_args
            self.assertIn("/channels/1003/messages", args[1])
            embed = kwargs["json"]["embeds"][0]
            self.assertIn("Stock bajo", embed["title"])


# --------------------------------------------------------------------------
# Routing Telegram → Discord
# --------------------------------------------------------------------------

class TelegramRoutingTests(TestCase):
    """``orders.telegram.notify_admin_about_order`` debe enviar a Discord
    cuando esté configurado, y a Telegram en caso contrario."""

    def _make_order(self):
        from catalog.models import Category, Plan, Product
        from orders.models import Order, OrderItem
        cat, _ = Category.objects.get_or_create(
            name="StreamingR", defaults={"slug": "r-stream"},
        )
        product, _ = Product.objects.get_or_create(
            slug="dp", defaults={"name": "Disney+", "category": cat},
        )
        plan, _ = Plan.objects.get_or_create(
            product=product, name="1 mes",
            defaults={
                "duration_days": 30,
                "price_customer": Decimal("7.00"),
                "price_distributor": Decimal("6.00"),
            },
        )
        o = Order.objects.create(
            email="r@example.com", currency="PEN",
            total=Decimal("7.00"), status="pending",
            payment_provider="yape",
        )
        OrderItem.objects.create(
            order=o, product=product, plan=plan,
            product_name=product.name, plan_name=plan.name,
            unit_price=Decimal("7.00"), quantity=1,
        )
        return o

    @override_settings(
        DISCORD_BOT_TOKEN="fake-token",
        DISCORD_CHANNEL_PEDIDOS="1001",
    )
    def test_routes_to_discord_when_configured(self):
        from orders import telegram as tg
        o = self._make_order()
        with patch("discord_bot.notifications.notify_new_order") as discord_fn, \
             patch.object(tg, "notify_admin") as tg_fn:
            tg.notify_admin_about_order(o)
            discord_fn.assert_called_once_with(o)
            tg_fn.assert_not_called()

    @override_settings(DISCORD_BOT_TOKEN="", DISCORD_CHANNEL_PEDIDOS="")
    def test_falls_back_to_telegram_when_discord_off(self):
        from orders import telegram as tg
        o = self._make_order()
        with patch("discord_bot.notifications.notify_new_order") as discord_fn, \
             patch.object(tg, "notify_admin") as tg_fn:
            tg.notify_admin_about_order(o)
            discord_fn.assert_not_called()
            tg_fn.assert_called_once()
