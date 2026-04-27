"""Tests para PR D — features de negocio."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from catalog.models import Category, Plan, Product, StockItem
from orders.models import Order, OrderItem


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
