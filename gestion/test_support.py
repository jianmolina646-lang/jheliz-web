from django.contrib.auth import get_user_model
from django.test import TestCase
from unittest import mock

from .models import Client, SupportContact, SupportMessage, SupportTicket
from .support_operations import add_message, create_ticket
from .telegram_alerts import _button, process_update


class SupportTicketTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user("support-owner", password="test")
        self.other = User.objects.create_user("support-other", password="test")
        self.client = Client.objects.create(owner=self.owner, name="Cliente uno")
        self.contact = SupportContact.objects.create(owner=self.owner, client=self.client)

    def test_ticket_is_numbered_per_owner_and_stores_message(self):
        first = create_ticket(self.contact, "access", "No puedo ingresar")
        second = create_ticket(self.contact, "password", "La clave no funciona")
        self.assertEqual(first.display_number, "S-0001")
        self.assertEqual(second.display_number, "S-0002")
        self.assertEqual(first.messages.get().sender, SupportMessage.Sender.CUSTOMER)

    def test_agent_reply_moves_ticket_to_waiting(self):
        ticket = create_ticket(self.contact, "other", "Necesito ayuda")
        add_message(ticket, SupportMessage.Sender.AGENT, "Ya lo revisamos")
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, SupportTicket.Status.WAITING)

    def test_ticket_remains_scoped_to_owner(self):
        ticket = create_ticket(self.contact, "other", "Privado")
        self.assertFalse(SupportTicket.objects.filter(owner=self.other, pk=ticket.pk).exists())

    def test_support_link_uses_requested_premium_emoji(self):
        button = _button("Enlace de soporte", "support_link:1")
        self.assertEqual(button["icon_custom_emoji_id"], "5307544885874664176")

    @mock.patch("gestion.telegram_alerts.send_message")
    def test_invalid_support_token_is_rejected_without_breaking_polling(self, send_message):
        process_update(
            {
                "message": {
                    "text": "/start support_abc123",
                    "chat": {"id": 12345},
                }
            }
        )
        send_message.assert_called_once()
        self.assertIn("no es válido", send_message.call_args.args[1])
