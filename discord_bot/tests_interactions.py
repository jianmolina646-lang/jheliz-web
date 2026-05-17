"""Tests para slash commands y verificación de firma."""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from discord_bot import interactions


# --------------------------------------------------------------------------
# Verificación de firma
# --------------------------------------------------------------------------

class VerifySignatureTests(TestCase):

    def test_returns_false_with_empty_inputs(self):
        self.assertFalse(interactions.verify_signature(b"", "", "", ""))

    def test_returns_false_on_bad_signature(self):
        # Genera un par de claves random pero pasamos una firma incorrecta.
        from nacl.signing import SigningKey

        sk = SigningKey.generate()
        pk_hex = sk.verify_key.encode().hex()
        body = b'{"type":1}'
        timestamp = "1700000000"
        bad_sig_hex = ("ff" * 64)  # 64 bytes = tamaño correcto pero firma falsa
        self.assertFalse(interactions.verify_signature(
            body, bad_sig_hex, timestamp, pk_hex,
        ))

    def test_returns_true_on_valid_signature(self):
        from nacl.signing import SigningKey

        sk = SigningKey.generate()
        pk_hex = sk.verify_key.encode().hex()
        body = b'{"type":1}'
        timestamp = "1700000000"
        sig = sk.sign(timestamp.encode() + body).signature
        self.assertTrue(interactions.verify_signature(
            body, sig.hex(), timestamp, pk_hex,
        ))


# --------------------------------------------------------------------------
# Dispatcher
# --------------------------------------------------------------------------

class HandleInteractionTests(TestCase):

    def test_ping_returns_pong(self):
        response = interactions.handle_interaction({"type": 1})
        self.assertEqual(response, {"type": 1})

    def test_unknown_command_returns_ephemeral_error(self):
        response = interactions.handle_interaction({
            "type": 2,
            "data": {"name": "inexistente"},
        })
        self.assertEqual(response["type"], 4)
        # 64 = FLAG_EPHEMERAL
        self.assertEqual(response["data"]["flags"], 64)
        self.assertIn("no implementado", response["data"]["content"])

    def _make_order(self, *, status="pending", email="t@example.com", total="10.00"):
        from catalog.models import Category, Plan, Product
        from orders.models import Order, OrderItem
        cat, _ = Category.objects.get_or_create(
            name="Streaming", defaults={"slug": "streaming"},
        )
        product, _ = Product.objects.get_or_create(
            slug=f"np-{status}-{email}",
            defaults={"name": f"Netflix {status}", "category": cat},
        )
        plan, _ = Plan.objects.get_or_create(
            product=product, name="1 mes",
            defaults={
                "duration_days": 30,
                "price_customer": Decimal(total),
                "price_distributor": Decimal("8.00"),
            },
        )
        order = Order.objects.create(
            email=email, currency="PEN",
            total=Decimal(total), status=status,
            payment_provider="yape",
        )
        OrderItem.objects.create(
            order=order, product=product, plan=plan,
            product_name=product.name, plan_name=plan.name,
            unit_price=Decimal(total), quantity=1,
        )
        return order

    def test_buscar_by_order_number(self):
        order = self._make_order()
        response = interactions.handle_interaction({
            "type": 2,
            "data": {
                "name": "buscar",
                "options": [{"name": "consulta", "value": f"JH-{order.pk:04d}"}],
            },
        })
        self.assertEqual(response["type"], 4)
        embed = response["data"]["embeds"][0]
        self.assertIn("Resultados", embed["title"])
        self.assertIn(f"JH-{order.pk:04d}", embed["description"])

    def test_buscar_by_email(self):
        self._make_order(email="hello@example.com")
        response = interactions.handle_interaction({
            "type": 2,
            "data": {
                "name": "buscar",
                "options": [{"name": "consulta", "value": "hello@example.com"}],
            },
        })
        embed = response["data"]["embeds"][0]
        self.assertIn("Resultados", embed["title"])

    def test_buscar_no_results(self):
        response = interactions.handle_interaction({
            "type": 2,
            "data": {
                "name": "buscar",
                "options": [{"name": "consulta", "value": "noexiste@example.com"}],
            },
        })
        self.assertIn("Sin resultados", response["data"]["content"])

    def test_buscar_empty_query(self):
        response = interactions.handle_interaction({
            "type": 2,
            "data": {
                "name": "buscar",
                "options": [{"name": "consulta", "value": ""}],
            },
        })
        self.assertIn("Decime qué buscar", response["data"]["content"])

    def test_pendientes_returns_open_orders(self):
        self._make_order(status="pending")
        self._make_order(status="verifying", email="b@example.com")
        self._make_order(status="delivered", email="c@example.com")
        response = interactions.handle_interaction({
            "type": 2,
            "data": {"name": "pendientes"},
        })
        embed = response["data"]["embeds"][0]
        # 2 pendientes (no el entregado)
        self.assertIn("Pendientes (2)", embed["title"])

    def test_pendientes_empty(self):
        response = interactions.handle_interaction({
            "type": 2,
            "data": {"name": "pendientes"},
        })
        self.assertIn("No hay pedidos pendientes", response["data"]["content"])

    def test_entregar_with_valid_number(self):
        order = self._make_order()
        response = interactions.handle_interaction({
            "type": 2,
            "data": {
                "name": "entregar",
                "options": [{"name": "numero", "value": f"JH-{order.pk:04d}"}],
            },
        })
        embed = response["data"]["embeds"][0]
        self.assertIn("Entregar", embed["title"])
        self.assertEqual(len(response["data"]["components"]), 1)

    def test_entregar_invalid_format(self):
        response = interactions.handle_interaction({
            "type": 2,
            "data": {
                "name": "entregar",
                "options": [{"name": "numero", "value": "abc"}],
            },
        })
        self.assertIn("Formato inválido", response["data"]["content"])

    def test_entregar_not_found(self):
        response = interactions.handle_interaction({
            "type": 2,
            "data": {
                "name": "entregar",
                "options": [{"name": "numero", "value": "JH-99999"}],
            },
        })
        self.assertIn("No encontré", response["data"]["content"])

    def test_stock_lists_plans(self):
        self._make_order()
        response = interactions.handle_interaction({
            "type": 2,
            "data": {"name": "stock"},
        })
        embed = response["data"]["embeds"][0]
        self.assertIn("Stock", embed["title"])


# --------------------------------------------------------------------------
# Webhook HTTP
# --------------------------------------------------------------------------

@override_settings(DISCORD_PUBLIC_KEY="ab" * 32)
class InteractionsWebhookTests(TestCase):
    """Smoke tests del endpoint público `/discord/interactions/`."""

    def setUp(self):
        self.url = reverse("discord_bot:interactions")
        self.client = Client()

    def test_rejects_missing_signature(self):
        resp = self.client.post(
            self.url, data=b'{"type":1}', content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_rejects_bad_signature(self):
        resp = self.client.post(
            self.url, data=b'{"type":1}', content_type="application/json",
            HTTP_X_SIGNATURE_ED25519="ff" * 64,
            HTTP_X_SIGNATURE_TIMESTAMP="1700000000",
        )
        self.assertEqual(resp.status_code, 401)

    def test_responds_to_ping_with_valid_signature(self):
        from nacl.signing import SigningKey

        sk = SigningKey.generate()
        pk_hex = sk.verify_key.encode().hex()

        with override_settings(DISCORD_PUBLIC_KEY=pk_hex):
            body = b'{"type":1}'
            timestamp = "1700000000"
            sig = sk.sign(timestamp.encode() + body).signature
            resp = self.client.post(
                self.url, data=body, content_type="application/json",
                HTTP_X_SIGNATURE_ED25519=sig.hex(),
                HTTP_X_SIGNATURE_TIMESTAMP=timestamp,
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(json.loads(resp.content), {"type": 1})

    @override_settings(DISCORD_PUBLIC_KEY="")
    def test_503_when_public_key_not_configured(self):
        resp = self.client.post(
            self.url, data=b'{"type":1}', content_type="application/json",
        )
        self.assertEqual(resp.status_code, 503)

    def test_get_method_not_allowed(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)
