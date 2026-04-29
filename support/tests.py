from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import ReplyTemplate, Ticket, TicketMessage


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


class AdminSupportChatTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="cliente", email="cliente@example.com", password="pwd1234!"
        )
        self.staff = User.objects.create_user(
            username="staffer", email="staff@example.com", password="pwd1234!",
            is_staff=True,
        )
        self.ticket = Ticket.objects.create(
            user=self.user, subject="Necesito ayuda", status=Ticket.Status.PENDING_ADMIN,
        )
        TicketMessage.objects.create(
            ticket=self.ticket, author=self.user, body="No puedo entrar a Netflix.",
        )

    def test_chat_view_requires_staff(self):
        self.client.force_login(self.user)
        url = reverse("admin_support_chat", args=[self.ticket.pk])
        resp = self.client.get(url)
        self.assertNotEqual(resp.status_code, 200)

    def test_chat_view_renders_for_staff(self):
        self.client.force_login(self.staff)
        url = reverse("admin_support_chat", args=[self.ticket.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No puedo entrar a Netflix.")
        self.assertContains(resp, 'id="ticket-messages"')

    def test_htmx_reply_creates_staff_message_and_returns_partial(self):
        self.client.force_login(self.staff)
        url = reverse("admin_support_chat_reply", args=[self.ticket.pk])
        resp = self.client.post(
            url, {"body": "Te ayudo enseguida."}, HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Te ayudo enseguida.")
        self.assertContains(resp, 'id="ticket-messages"')
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.Status.PENDING_USER)
        last = self.ticket.messages.order_by("-created_at").first()
        self.assertTrue(last.is_from_staff)
        self.assertEqual(last.author, self.staff)

    def test_template_id_renders_template_when_body_empty(self):
        tpl = ReplyTemplate.objects.create(
            name="Saludo", category=ReplyTemplate.Category.GENERAL,
            body="Hola {nombre}, gracias por escribir.", is_active=True,
        )
        self.client.force_login(self.staff)
        url = reverse("admin_support_chat_reply", args=[self.ticket.pk])
        resp = self.client.post(
            url, {"body": "", "template_id": str(tpl.pk)},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        last = self.ticket.messages.order_by("-created_at").first()
        self.assertIn("gracias por escribir", last.body)
        tpl.refresh_from_db()
        self.assertEqual(tpl.use_count, 1)
        self.assertIsNotNone(tpl.last_used_at)

    def test_empty_body_without_template_returns_400_for_htmx(self):
        self.client.force_login(self.staff)
        url = reverse("admin_support_chat_reply", args=[self.ticket.pk])
        resp = self.client.post(url, {"body": "   "}, HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.ticket.messages.count(), 1)

    def test_messages_endpoint_requires_staff(self):
        url = reverse("admin_support_chat_messages", args=[self.ticket.pk])
        self.client.force_login(self.user)
        resp = self.client.get(url)
        self.assertNotEqual(resp.status_code, 200)
        self.client.force_login(self.staff)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="ticket-messages"')
