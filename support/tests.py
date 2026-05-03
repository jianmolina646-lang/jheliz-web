from django.contrib.auth import get_user_model
from django.db.models import F
from django.test import TestCase
from django.urls import reverse

from .models import CodeRequest, ReplyTemplate, Ticket, TicketMessage


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

    def test_admin_chat_polls_admin_endpoint_not_customer_one(self):
        """El partial del admin debe pollear el endpoint admin, no el del cliente."""
        self.client.force_login(self.staff)
        url = reverse("admin_support_chat", args=[self.ticket.pk])
        resp = self.client.get(url)
        admin_poll = reverse("admin_support_chat_messages", args=[self.ticket.pk])
        customer_poll = reverse("support:messages", args=[self.ticket.pk])
        self.assertContains(resp, f'hx-get="{admin_poll}"')
        self.assertNotContains(resp, f'hx-get="{customer_poll}"')

    def test_customer_chat_still_polls_customer_endpoint(self):
        """Regresión: el cliente sigue pollando su propio endpoint."""
        self.client.force_login(self.user)
        url = reverse("support:detail", args=[self.ticket.pk])
        resp = self.client.get(url)
        customer_poll = reverse("support:messages", args=[self.ticket.pk])
        self.assertContains(resp, f'hx-get="{customer_poll}"')

    def test_template_use_count_survives_concurrent_update(self):
        """Race condition: si la BD cambia entre fetch y save del request, F() lo absorbe."""
        tpl = ReplyTemplate.objects.create(
            name="Saludo", category=ReplyTemplate.Category.GENERAL,
            body="Hola.", is_active=True, use_count=5,
        )
        self.client.force_login(self.staff)
        url = reverse("admin_support_chat_reply", args=[self.ticket.pk])
        # Simulamos otro worker incrementando el contador mientras el request está en
        # vuelo: monkey-patch ReplyTemplate.save para meter +1 directo en BD justo
        # antes del save real.
        original_save = ReplyTemplate.save

        def racing_save(self, *args, **kwargs):
            ReplyTemplate.objects.filter(pk=self.pk).update(use_count=F("use_count") + 1)
            return original_save(self, *args, **kwargs)

        ReplyTemplate.save = racing_save
        try:
            self.client.post(
                url, {"body": "a", "template_id": str(tpl.pk)},
                HTTP_HX_REQUEST="true",
            )
        finally:
            ReplyTemplate.save = original_save

        tpl.refresh_from_db()
        # Con F(): 5 + 1 (otro worker) + 1 (request) = 7. Con read-modify-write
        # ingenuo: 5 + 1 (otro) + 1 (request usa el 5 cacheado) = 6. Esperamos 7.
        self.assertEqual(tpl.use_count, 7)


class CodeRequestViewsTests(TestCase):
    """Tests del verificador de códigos (flujo manual)."""

    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="admin", email="admin@example.com", password="pwd1234!",
            is_staff=True,
        )

    def _post_create(self, **overrides):
        data = {
            "platform": CodeRequest.Platform.NETFLIX,
            "requested_code_type": "login",
            "account_email": "jheliz-netflix1@gmail.com",
            "contact_email": "",
            "order_number": "",
            "note": "",
        }
        data.update(overrides)
        return self.client.post(reverse("code_create"), data)

    def test_customer_create_form_renders(self):
        resp = self.client.get(reverse("code_create"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Verificador de")
        self.assertContains(resp, "Plataforma")

    def test_customer_create_persists_and_redirects_to_status(self):
        resp = self._post_create()
        self.assertEqual(resp.status_code, 302)
        cr = CodeRequest.objects.get()
        self.assertEqual(cr.status, CodeRequest.Status.PENDING)
        self.assertEqual(cr.audience, CodeRequest.Audience.CUSTOMER)
        self.assertIn(reverse("code_status", args=[cr.token]), resp["Location"])

    def test_status_page_shows_pending(self):
        self._post_create()
        cr = CodeRequest.objects.get()
        resp = self.client.get(reverse("code_status", args=[cr.token]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Esperando tu código")

    def test_status_json_pending(self):
        self._post_create()
        cr = CodeRequest.objects.get()
        resp = self.client.get(reverse("code_status_json", args=[cr.token]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["code"], "")

    def test_status_json_delivered_shows_code(self):
        self._post_create()
        cr = CodeRequest.objects.get()
        cr.code = "1234"
        cr.code_type = CodeRequest.CodeType.LOGIN
        cr.mark_delivered(by_user=self.staff)
        resp = self.client.get(reverse("code_status_json", args=[cr.token]))
        data = resp.json()
        self.assertEqual(data["status"], "delivered")
        self.assertEqual(data["code"], "1234")
        self.assertIn("sesión", data["code_type"].lower())

    def test_rate_limit_blocks_repeated_requests(self):
        # Crea 3 en la ventana y el 4º debería fallar por rate limit.
        for _ in range(3):
            self._post_create()
        resp = self._post_create()
        self.assertEqual(resp.status_code, 200)  # vuelve a renderizar con error
        self.assertContains(resp, "muchas solicitudes")
        self.assertEqual(CodeRequest.objects.count(), 3)

    def test_distributor_route_requires_permission(self):
        User = get_user_model()
        plain = User.objects.create_user(
            username="plain", email="plain@example.com", password="pwd1234!",
        )
        self.client.force_login(plain)
        resp = self.client.get(reverse("code_distrib_create"))
        self.assertEqual(resp.status_code, 404)

    def test_distributor_route_works_for_staff(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("code_distrib_create"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Plataforma")

    def test_distributor_create_marks_audience(self):
        self.client.force_login(self.staff)
        resp = self.client.post(reverse("code_distrib_create"), {
            "platform": CodeRequest.Platform.DISNEY,
            "requested_code_type": "device",
            "account_email": "distrib@example.com",
            "contact_email": "",
            "order_number": "",
            "note": "",
        })
        self.assertEqual(resp.status_code, 302)
        cr = CodeRequest.objects.get()
        self.assertEqual(cr.audience, CodeRequest.Audience.DISTRIBUTOR)
        self.assertEqual(cr.user_id, self.staff.id)

    def test_requested_code_type_is_required(self):
        resp = self.client.post(reverse("code_create"), {
            "platform": CodeRequest.Platform.NETFLIX,
            "requested_code_type": "",  # vacío
            "account_email": "x@y.com",
            "contact_email": "",
            "order_number": "",
            "note": "",
        })
        self.assertEqual(resp.status_code, 200)  # error, re-render
        self.assertEqual(CodeRequest.objects.count(), 0)

    def test_requested_code_type_persists_on_create(self):
        self._post_create(requested_code_type="device", note="Mi smart tv LG")
        cr = CodeRequest.objects.get()
        self.assertEqual(cr.requested_code_type, "device")
        self.assertEqual(cr.note, "Mi smart tv LG")

    def test_model_mark_delivered_sets_responded_at(self):
        cr = CodeRequest.objects.create(
            platform=CodeRequest.Platform.PRIME,
            account_email="a@b.com",
            audience=CodeRequest.Audience.CUSTOMER,
        )
        self.assertIsNone(cr.responded_at)
        cr.code = "7777"
        cr.code_type = CodeRequest.CodeType.LOGIN
        cr.mark_delivered(by_user=self.staff)
        self.assertIsNotNone(cr.responded_at)
        self.assertEqual(cr.responded_by_id, self.staff.id)
        self.assertEqual(cr.status, CodeRequest.Status.DELIVERED)
