import hashlib
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from gestion.models import Client, Service, Subscription, TelegramConnection
from gestion.telegram_alerts import link_chat, send_expiry_digests


class TelegramAlertTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user("revendedor", password="x")
        self.other = User.objects.create_user("otro", password="x")

    def test_one_time_token_links_only_its_owner(self):
        raw = "token-seguro"
        connection = TelegramConnection.objects.create(
            owner=self.owner,
            link_token_digest=hashlib.sha256(raw.encode()).hexdigest(),
            link_expires_at=timezone.now() + timedelta(minutes=10),
        )
        self.assertTrue(link_chat(raw, {"id": 123, "username": "revendedor"}))
        connection.refresh_from_db()
        self.assertEqual(connection.chat_id, "123")
        self.assertEqual(connection.link_token_digest, "")
        self.assertFalse(link_chat(raw, {"id": 999}))

    @patch("gestion.telegram_alerts.send_message")
    def test_digest_never_includes_another_owners_clients(self, send):
        today = timezone.localdate()
        for owner, client_name in ((self.owner, "Cliente propio"), (self.other, "Cliente ajeno")):
            service = Service.objects.create(owner=owner, name=f"Netflix {owner.pk}")
            client = Client.objects.create(owner=owner, name=client_name)
            Subscription.objects.create(
                owner=owner,
                client=client,
                service=service,
                account_email=f"{owner.pk}@example.com",
                starts_at=timezone.now(),
                expires_at=timezone.now(),
            )
        TelegramConnection.objects.create(owner=self.owner, chat_id="123", notify_windows=[0])

        self.assertEqual(send_expiry_digests(today), 1)
        message = send.call_args.args[1]
        self.assertIn("Cliente propio", message)
        self.assertNotIn("Cliente ajeno", message)

    @patch("gestion.telegram_alerts.send_message")
    def test_digest_rejects_cross_owner_relations_even_if_row_is_corrupt(self, send):
        own_service = Service.objects.create(owner=self.owner, name="Netflix propio")
        foreign_service = Service.objects.create(owner=self.other, name="Netflix ajeno")
        own_client = Client.objects.create(owner=self.owner, name="Cliente propio")
        foreign_client = Client.objects.create(owner=self.other, name="Cliente ajeno")
        common = {
            "owner": self.owner,
            "account_email": "cuenta@example.com",
            "starts_at": timezone.now(),
            "expires_at": timezone.now(),
        }
        Subscription.objects.create(
            client=own_client,
            service=own_service,
            **common,
        )
        # Filas deliberadamente inconsistentes: owner=A, relación=B.
        Subscription.objects.create(
            client=foreign_client,
            service=own_service,
            **common,
        )
        Subscription.objects.create(
            client=own_client,
            service=foreign_service,
            **common,
        )
        TelegramConnection.objects.create(
            owner=self.owner,
            chat_id="123",
            notify_windows=[0],
        )

        self.assertEqual(send_expiry_digests(timezone.localdate()), 1)
        message = send.call_args.args[1]
        self.assertEqual(message.count("Cliente propio"), 1)
        self.assertNotIn("Cliente ajeno", message)
        self.assertNotIn("Netflix ajeno", message)
