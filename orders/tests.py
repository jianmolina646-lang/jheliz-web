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


"""Tests para PR D — features de negocio."""


from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from catalog.models import Category, Plan, Product, StockItem


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


# ----- PR D -----

def _make_setup():
    cat = Category.objects.create(name="Streaming", slug="streaming")
    product = Product.objects.create(
        name="Netflix Premium", slug="netflix-premium", category=cat
    )
    plan = Plan.objects.create(
        product=product, name="1 mes", duration_days=30,
        price_customer=Decimal("15.00"), price_distributor=Decimal("12.00"),
        low_stock_threshold=3,
    )
    return product, plan


def _make_delivered_item(*, days_until_expiry: int, email: str = "cliente@ejemplo.com"):
    product, plan = _make_setup()
    order = Order.objects.create(
        email=email, total=Decimal("15.00"), status=Order.Status.DELIVERED,
    )
    return OrderItem.objects.create(
        order=order,
        product=product,
        plan=plan,
        product_name=product.name,
        plan_name=plan.name,
        unit_price=plan.price_customer,
        quantity=1,
        expires_at=timezone.now() + timedelta(days=days_until_expiry),
    )


class ExpiryReminderTests(TestCase):
    def test_sends_3d_reminder(self):
        item = _make_delivered_item(days_until_expiry=3)
        out = StringIO()
        call_command("send_expiry_reminders", stdout=out)
        item.refresh_from_db()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("3 días", mail.outbox[0].subject)
        self.assertIsNotNone(item.expiry_reminder_3d_sent_at)

    def test_sends_1d_reminder(self):
        item = _make_delivered_item(days_until_expiry=1)
        call_command("send_expiry_reminders", stdout=StringIO())
        item.refresh_from_db()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("mañana", mail.outbox[0].subject)
        self.assertIsNotNone(item.expiry_reminder_1d_sent_at)

    def test_does_not_resend(self):
        _make_delivered_item(days_until_expiry=3)
        call_command("send_expiry_reminders", stdout=StringIO())
        call_command("send_expiry_reminders", stdout=StringIO())
        # Sólo una vez:
        self.assertEqual(len(mail.outbox), 1)

    def test_dry_run_does_not_send(self):
        item = _make_delivered_item(days_until_expiry=3)
        call_command("send_expiry_reminders", "--dry-run", stdout=StringIO())
        item.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNone(item.expiry_reminder_3d_sent_at)

    def test_skips_orders_without_email(self):
        _make_delivered_item(days_until_expiry=3, email="")
        call_command("send_expiry_reminders", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)

    def test_skips_non_delivered_orders(self):
        item = _make_delivered_item(days_until_expiry=3)
        item.order.status = Order.Status.PENDING
        item.order.save()
        call_command("send_expiry_reminders", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)


class LowStockAlertTests(TestCase):
    def setUp(self):
        self.product, self.plan = _make_setup()

    def _add_stock(self, n: int):
        for i in range(n):
            StockItem.objects.create(
                product=self.product, plan=self.plan,
                credentials=f"creds-{i}",
            )

    @patch("orders.telegram.notify_admin")
    def test_alert_when_below_threshold(self, mock_notify):
        self._add_stock(2)  # umbral es 3
        with patch("orders.telegram.is_configured", return_value=True):
            call_command("check_low_stock", stdout=StringIO())
        mock_notify.assert_called_once()
        msg = mock_notify.call_args[0][0]
        self.assertIn("Netflix Premium", msg)
        self.assertIn("2/3", msg)
        self.plan.refresh_from_db()
        self.assertIsNotNone(self.plan.low_stock_alert_sent_at)

    @patch("orders.telegram.notify_admin")
    def test_no_alert_when_at_threshold(self, mock_notify):
        self._add_stock(3)
        with patch("orders.telegram.is_configured", return_value=True):
            call_command("check_low_stock", stdout=StringIO())
        mock_notify.assert_not_called()

    @patch("orders.telegram.notify_admin")
    def test_does_not_realert_within_cooldown(self, mock_notify):
        self._add_stock(1)
        with patch("orders.telegram.is_configured", return_value=True):
            call_command("check_low_stock", stdout=StringIO())
            call_command("check_low_stock", stdout=StringIO())
        self.assertEqual(mock_notify.call_count, 1)

    @patch("orders.telegram.notify_admin")
    def test_clears_flag_when_stock_recovers(self, mock_notify):
        self._add_stock(1)
        with patch("orders.telegram.is_configured", return_value=True):
            call_command("check_low_stock", stdout=StringIO())
        self.plan.refresh_from_db()
        self.assertIsNotNone(self.plan.low_stock_alert_sent_at)

        # Repón stock
        self._add_stock(5)
        with patch("orders.telegram.is_configured", return_value=True):
            call_command("check_low_stock", stdout=StringIO())
        self.plan.refresh_from_db()
        self.assertIsNone(self.plan.low_stock_alert_sent_at)


class AuditLogTests(TestCase):
    def test_orderitem_changes_create_log_entries(self):
        from auditlog.models import LogEntry

        item = _make_delivered_item(days_until_expiry=10)
        # La creación ya generó una entrada:
        self.assertGreaterEqual(
            LogEntry.objects.get_for_object(item).count(), 1
        )
        item.delivered_credentials = "secreto"
        item.save()
        # El cambio en delivered_credentials NO se guarda en el log
        # (configurado en orders.apps.OrdersConfig.ready):
        latest = LogEntry.objects.get_for_object(item).order_by("-timestamp").first()
        if latest and latest.changes_dict:
            self.assertNotIn("delivered_credentials", latest.changes_dict)
