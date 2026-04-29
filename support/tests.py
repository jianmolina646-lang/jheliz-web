from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Ticket, TicketMessage


class SupportChatViewsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="cliente", email="cliente@example.com", password="pwd1234!"
        )
        self.staff = User.objects.create_user(
            username="staffer", email="staff@example.com", password="pwd1234!", is_staff=True
        )
        self.ticket = Ticket.objects.create(
            user=self.user, subject="Necesito ayuda", status=Ticket.Status.PENDING_ADMIN
        )
        TicketMessage.objects.create(
            ticket=self.ticket, author=self.user, body="Hola, no puedo entrar a Netflix.",
        )

    def test_messages_endpoint_returns_partial(self):
        self.client.force_login(self.user)
        url = reverse("support:messages", args=[self.ticket.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "no puedo entrar a Netflix")
        self.assertContains(resp, 'id="ticket-messages"')

    def test_other_user_cannot_view_messages(self):
        User = get_user_model()
        other = User.objects.create_user(
            username="ajeno", email="ajeno@example.com", password="pwd1234!"
        )
        self.client.force_login(other)
        url = reverse("support:messages", args=[self.ticket.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_htmx_reply_returns_messages_partial_and_creates_message(self):
        self.client.force_login(self.user)
        url = reverse("support:reply", args=[self.ticket.pk])
        resp = self.client.post(
            url, {"body": "Sigue sin funcionar."}, HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Sigue sin funcionar.")
        self.assertContains(resp, 'id="ticket-messages"')
        self.assertEqual(self.ticket.messages.count(), 2)

    def test_staff_reply_marks_status_pending_user(self):
        self.client.force_login(self.staff)
        url = reverse("support:reply", args=[self.ticket.pk])
        self.client.post(url, {"body": "Te ayudo enseguida."}, HTTP_HX_REQUEST="true")
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.Status.PENDING_USER)
        last = self.ticket.messages.order_by("-created_at").first()
        self.assertTrue(last.is_from_staff)

    def test_non_htmx_reply_redirects_to_detail(self):
        self.client.force_login(self.user)
        url = reverse("support:reply", args=[self.ticket.pk])
        resp = self.client.post(url, {"body": "Otro mensaje."})
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("support:detail", args=[self.ticket.pk]), resp["Location"])
