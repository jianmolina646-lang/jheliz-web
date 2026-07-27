import hashlib
import hmac
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import (
    Client, Service, Subscription, WhatsAppConnection, WhatsAppReminderDelivery,
)
from .whatsapp import process_webhook, send_due_reminders, verify_signature


@override_settings(META_APP_SECRET="test-secret")
class WhatsAppAutomationTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user("seller", password="x")
        self.client_obj = Client.objects.create(
            owner=self.owner, name="Ana", whatsapp="+51987654321",
            whatsapp_opt_in_at=timezone.now(),
        )
        self.service = Service.objects.create(owner=self.owner, name="Netflix")
        self.subscription = Subscription.objects.create(
            owner=self.owner, client=self.client_obj, service=self.service,
            account_email="ana@example.com",
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.connection = WhatsAppConnection.objects.create(
            owner=self.owner, access_token="tenant-token", waba_id="waba-1",
            phone_number_id="phone-1", status=WhatsAppConnection.Status.ACTIVE,
            reminder_days=[1],
        )

    def test_webhook_signature(self):
        body = b'{"object":"whatsapp_business_account"}'
        digest = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_signature(body, f"sha256={digest}"))
        self.assertFalse(verify_signature(body, "sha256=wrong"))

    @patch("gestion.whatsapp.send_template", return_value="wamid.123")
    def test_reminder_is_idempotent(self, send):
        today = timezone.localdate()
        self.assertEqual(send_due_reminders(today), 1)
        self.assertEqual(send_due_reminders(today), 0)
        self.assertEqual(send.call_count, 1)
        delivery = WhatsAppReminderDelivery.objects.get()
        self.assertEqual(delivery.status, WhatsAppReminderDelivery.Status.SENT)
        args = send.call_args.args[2]
        self.assertEqual(args[2], "ana***@example.com")

    @patch("gestion.whatsapp.send_template", return_value="wamid.no-consent")
    def test_client_without_consent_is_skipped(self, send):
        self.client_obj.whatsapp_opt_in_at = None
        self.client_obj.save(update_fields=["whatsapp_opt_in_at"])
        self.assertEqual(send_due_reminders(timezone.localdate()), 0)
        send.assert_not_called()

    def test_webhook_updates_delivery_status(self):
        delivery = WhatsAppReminderDelivery.objects.create(
            owner=self.owner, subscription=self.subscription,
            expiry_date=timezone.localdate() + timedelta(days=1),
            reminder_days=1, recipient="51987654321",
            template_name="recordatorio_vencimiento",
            meta_message_id="wamid.123",
        )
        payload = {
            "entry": [{"changes": [{"value": {
                "statuses": [{"id": "wamid.123", "status": "delivered"}],
            }}]}],
        }
        self.assertEqual(process_webhook(payload), 1)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, WhatsAppReminderDelivery.Status.DELIVERED)
        self.assertIsNotNone(delivery.delivered_at)
