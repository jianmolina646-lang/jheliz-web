"""Smoke tests para las mejoras de seguridad del PR A.

- Cifrado transparente de OrderItem.delivered_credentials.
- Compatibilidad backwards con datos en texto plano.
- Auth requerido en /media/payments/proofs/.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Plan, Product
from orders.encryption import EncryptedTextField, decrypt_text, encrypt_text
from orders.models import Order, OrderItem


def _make_order_item(creds: str = "") -> OrderItem:
    cat = Category.objects.create(name="Streaming", slug="streaming")
    product = Product.objects.create(
        name="Netflix Premium", slug="netflix-premium", category=cat
    )
    plan = Plan.objects.create(
        product=product, name="1 mes", duration_days=30,
        price_customer=Decimal("15.00"), price_distributor=Decimal("12.00"),
    )
    order = Order.objects.create(email="cliente@ejemplo.com", total=Decimal("15.00"))
    return OrderItem.objects.create(
        order=order,
        product=product,
        plan=plan,
        product_name=product.name,
        plan_name=plan.name,
        unit_price=plan.price_customer,
        quantity=1,
        delivered_credentials=creds,
    )


class EncryptedFieldTests(TestCase):
    def test_roundtrip(self):
        secret = "email: foo@bar.com\nclave: SuperSecreta123"
        token = encrypt_text(secret)
        self.assertNotEqual(token, secret)
        self.assertTrue(token.startswith("gAAAAA"))
        self.assertEqual(decrypt_text(token), secret)

    def test_field_stores_ciphertext_in_db(self):
        item = _make_order_item("email: foo@bar.com\nclave: secret")
        with connection.cursor() as cur:
            cur.execute(
                "SELECT delivered_credentials FROM orders_orderitem WHERE id = %s",
                [item.pk],
            )
            raw = cur.fetchone()[0]
        # Lo que está en la BD NO es texto plano:
        self.assertNotIn("clave: secret", raw)
        self.assertTrue(raw.startswith("gAAAAA"))

    def test_field_decrypts_on_read(self):
        item = _make_order_item("PIN: 1234")
        item.refresh_from_db()
        self.assertEqual(item.delivered_credentials, "PIN: 1234")

    def test_legacy_plaintext_is_returned_as_is(self):
        item = _make_order_item("placeholder")
        # Sobrescribimos directamente con SQL para simular fila legacy en plano:
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE orders_orderitem SET delivered_credentials = %s WHERE id = %s",
                ["TEXTO_PLANO_LEGACY", item.pk],
            )
        item.refresh_from_db()
        self.assertEqual(item.delivered_credentials, "TEXTO_PLANO_LEGACY")

    def test_field_is_subclass_of_textfield(self):
        from django.db import models
        self.assertTrue(issubclass(EncryptedTextField, models.TextField))


@override_settings(MEDIA_ROOT="/tmp/jheliz-test-media")
class PaymentProofAuthTests(TestCase):
    def setUp(self):
        import os
        path = os.path.join(settings.MEDIA_ROOT, "payments", "proofs")
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "test.txt"), "wb") as f:
            f.write(b"comprobante secreto")
        self.url = "/media/payments/proofs/test.txt"

    def test_anonymous_redirected_to_login(self):
        c = Client()
        resp = c.get(self.url)
        self.assertEqual(resp.status_code, 302)
        # LOGIN_URL es "accounts:login" → resuelve a /cuenta/ingresar/.
        self.assertIn("/cuenta/", resp["Location"])
        self.assertIn("next=", resp["Location"])

    def test_non_staff_user_forbidden(self):
        User = get_user_model()
        u = User.objects.create_user(username="cliente", password="x" * 12)
        c = Client()
        c.force_login(u)
        resp = c.get(self.url)
        # user_passes_test redirige al login si falla la condición:
        self.assertEqual(resp.status_code, 302)

    def test_staff_user_can_read(self):
        User = get_user_model()
        u = User.objects.create_user(username="staff", password="x" * 12, is_staff=True)
        c = Client()
        c.force_login(u)
        resp = c.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(b"".join(resp.streaming_content), b"comprobante secreto")
