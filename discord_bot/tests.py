from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings

from discord_bot import client, notifications


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


class NotifyNewCodeRequestTests(TestCase):
    """Comprueba que notify_new_code_request arme el embed correctamente."""

    @override_settings(DISCORD_BOT_TOKEN="", DISCORD_CHANNEL_CODIGOS="")
    def test_no_op_when_token_missing(self):
        # Sin token, debe devolver None sin llamar a la API.
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
            self.assertEqual(args[0], "POST")
            self.assertIn("/channels/9999/messages", args[1])
            payload = kwargs["json"]
            self.assertIn("embeds", payload)
            embed = payload["embeds"][0]
            self.assertIn("Nuevo pedido de código", embed["title"])

            fields_text = " ".join(
                f"{f['name']}={f['value']}" for f in embed["fields"]
            )
            self.assertIn("Netflix", fields_text)
            self.assertIn("t@example.com", fields_text)
            self.assertIn("JH-0042", fields_text)
            self.assertIn("Cusco", fields_text)
