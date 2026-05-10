"""Tests del chat en vivo (público + admin)."""

from datetime import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from .models import ChatMessage, ChatRoom
from .templatetags.livechat import livechat_is_online


User = get_user_model()


class PublicChatFlowTests(TestCase):
    """Flujo del visitante: start → send → poll."""

    def setUp(self):
        self.client = Client()

    def test_start_creates_new_room_when_no_token(self):
        resp = self.client.post(
            "/chat/start/",
            data={"name": "Juan", "email": "juan@example.com"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertIn("token", data["room"])
        self.assertEqual(data["room"]["customer_name"], "Juan")
        self.assertEqual(data["room"]["customer_email"], "juan@example.com")
        self.assertEqual(ChatRoom.objects.count(), 1)

    def test_start_resumes_existing_room_with_token(self):
        room = ChatRoom.objects.create(
            customer_name="Vieja", customer_email="x@example.com",
        )
        resp = self.client.post(
            "/chat/start/", data={"token": room.token},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["room"]["token"], room.token)
        self.assertEqual(ChatRoom.objects.count(), 1)

    def test_start_rejects_invalid_email(self):
        resp = self.client.post(
            "/chat/start/", data={"email": "not-an-email"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["ok"])

    def test_send_message_creates_message_and_touches_room(self):
        room = ChatRoom.objects.create(customer_email="a@b.com")
        resp = self.client.post(
            f"/chat/{room.token}/send/",
            data={"body": "hola necesito ayuda"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(ChatMessage.objects.count(), 1)
        msg = ChatMessage.objects.first()
        self.assertEqual(msg.sender, ChatMessage.Sender.CUSTOMER)
        self.assertEqual(msg.body, "hola necesito ayuda")
        room.refresh_from_db()
        self.assertIsNotNone(room.last_message_at)

    def test_send_rejects_empty_body(self):
        room = ChatRoom.objects.create(customer_email="a@b.com")
        resp = self.client.post(
            f"/chat/{room.token}/send/", data={"body": "   "},
        )
        self.assertEqual(resp.status_code, 400)

    def test_send_accepts_image_attachment(self):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        room = ChatRoom.objects.create(customer_email="a@b.com")
        buf = BytesIO()
        Image.new("RGB", (32, 32), color=(255, 0, 128)).save(buf, format="JPEG")
        buf.seek(0)
        img = SimpleUploadedFile(
            "captura.jpg", buf.getvalue(), content_type="image/jpeg",
        )
        resp = self.client.post(
            f"/chat/{room.token}/send/", data={"image": img},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertIsNotNone(data["message"]["image_url"])
        self.assertEqual(ChatMessage.objects.count(), 1)
        msg = ChatMessage.objects.first()
        self.assertTrue(bool(msg.image))

    def test_send_rejects_oversized_image(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        room = ChatRoom.objects.create(customer_email="a@b.com")
        # 6 MB de bytes — supera el límite de 5 MB
        big = SimpleUploadedFile(
            "big.jpg", b"x" * (6 * 1024 * 1024), content_type="image/jpeg",
        )
        resp = self.client.post(
            f"/chat/{room.token}/send/", data={"body": "hola", "image": big},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("grande", resp.json()["error"])

    def test_send_rejects_bad_image_mime(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        room = ChatRoom.objects.create(customer_email="a@b.com")
        bad = SimpleUploadedFile(
            "doc.pdf", b"%PDF-1.4 fake", content_type="application/pdf",
        )
        resp = self.client.post(
            f"/chat/{room.token}/send/", data={"body": "x", "image": bad},
        )
        self.assertEqual(resp.status_code, 400)

    def test_send_404_for_invalid_token(self):
        resp = self.client.post(
            "/chat/no-existe-este-token-12345/send/",
            data={"body": "x"},
        )
        # Token inválido (formato) o sala no encontrada → 404.
        self.assertEqual(resp.status_code, 404)

    def test_poll_returns_only_new_messages(self):
        room = ChatRoom.objects.create(customer_email="a@b.com")
        m1 = ChatMessage.objects.create(
            room=room, sender=ChatMessage.Sender.ADMIN, body="primer admin",
        )
        m2 = ChatMessage.objects.create(
            room=room, sender=ChatMessage.Sender.ADMIN, body="segundo admin",
        )
        resp = self.client.get(
            f"/chat/{room.token}/poll/?since_id={m1.id}",
        )
        self.assertEqual(resp.status_code, 200)
        ids = [m["id"] for m in resp.json()["messages"]]
        self.assertEqual(ids, [m2.id])


class AdminChatTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(
            username="admin1",
            email="admin@x.com",
            password="pwd",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.staff)

    def test_chat_index_lists_open_rooms(self):
        ChatRoom.objects.create(customer_email="cliente1@x.com")
        ChatRoom.objects.create(
            customer_email="cliente2@x.com",
            status=ChatRoom.Status.CLOSED,
        )
        resp = self.client.get(reverse("admin_livechat_index"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "cliente1@x.com")
        self.assertNotContains(resp, "cliente2@x.com")

    def test_chat_index_with_closed_filter_shows_all(self):
        ChatRoom.objects.create(customer_email="abierta@x.com")
        ChatRoom.objects.create(
            customer_email="cerrada@x.com", status=ChatRoom.Status.CLOSED,
        )
        resp = self.client.get(reverse("admin_livechat_index") + "?closed=1")
        self.assertContains(resp, "abierta@x.com")
        self.assertContains(resp, "cerrada@x.com")

    def test_admin_reply_creates_admin_message(self):
        room = ChatRoom.objects.create(customer_email="a@b.com")
        resp = self.client.post(
            reverse("admin_livechat_reply", args=[room.pk]),
            data={"body": "Te ayudo ya mismo."},
        )
        self.assertIn(resp.status_code, (200, 302))
        self.assertEqual(ChatMessage.objects.count(), 1)
        msg = ChatMessage.objects.first()
        self.assertEqual(msg.sender, ChatMessage.Sender.ADMIN)
        self.assertEqual(msg.sender_user, self.staff)

    def test_admin_close_and_reopen(self):
        room = ChatRoom.objects.create(customer_email="a@b.com")
        self.client.post(reverse("admin_livechat_close", args=[room.pk]))
        room.refresh_from_db()
        self.assertEqual(room.status, ChatRoom.Status.CLOSED)
        self.client.post(reverse("admin_livechat_reopen", args=[room.pk]))
        room.refresh_from_db()
        self.assertEqual(room.status, ChatRoom.Status.OPEN)

    def test_admin_unread_count_endpoint(self):
        room = ChatRoom.objects.create(customer_email="a@b.com")
        ChatMessage.objects.create(
            room=room, sender=ChatMessage.Sender.CUSTOMER, body="hola",
        )
        ChatMessage.objects.create(
            room=room, sender=ChatMessage.Sender.CUSTOMER, body="hola2",
        )
        resp = self.client.get(reverse("admin_livechat_unread_count"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_unread"], 2)
        self.assertEqual(data["rooms_with_unread"], 1)

    def test_messages_partial_marks_admin_seen(self):
        room = ChatRoom.objects.create(customer_email="a@b.com")
        ChatMessage.objects.create(
            room=room, sender=ChatMessage.Sender.CUSTOMER, body="ping",
        )
        self.assertEqual(room.admin_unread_count, 1)
        self.client.get(reverse("admin_livechat_messages", args=[room.pk]))
        room.refresh_from_db()
        self.assertEqual(room.admin_unread_count, 0)

    def test_unauthenticated_admin_endpoints_redirect(self):
        self.client.logout()
        resp = self.client.get(reverse("admin_livechat_index"))
        self.assertEqual(resp.status_code, 302)

    def test_chat_detail_loads_htmx_script(self):
        """Regression: el form de respuesta usa hx-post; sin htmx cargado el
        navegador hacía un POST regular y la página se recargaba (= "se va a
        otra pantalla"). Verifica que el template carga el bundle de htmx."""
        room = ChatRoom.objects.create(customer_email="a@b.com")
        resp = self.client.get(reverse("admin_livechat_detail", args=[room.pk]))
        self.assertEqual(resp.status_code, 200)
        # Django agrega un hash al filename via ManifestStaticFilesStorage,
        # por eso buscamos el prefijo "htmx.min" (matchea htmx.min.js o
        # htmx.min.<hash>.js)
        self.assertIn(b"htmx.min", resp.content)

    def test_chat_reply_with_htmx_returns_partial(self):
        """Cuando el form se manda con HX-Request=true, la vista devuelve
        sólo el partial del thread (no redirige)."""
        room = ChatRoom.objects.create(customer_email="a@b.com")
        resp = self.client.post(
            reverse("admin_livechat_reply", args=[room.pk]),
            data={"body": "Hola"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        # Tiene que ser el partial, no una redirección.
        self.assertContains(resp, 'id="livechat-thread"')
        self.assertContains(resp, "Hola")


class TelegramNotifyTests(TestCase):
    """Notificación al admin por Telegram cuando llega un mensaje del cliente."""

    def setUp(self):
        cache.clear()

    @patch("livechat.telegram_notify.cache")
    @patch("orders.telegram.notify_admin")
    @patch("orders.telegram.is_configured", return_value=True)
    def test_send_triggers_telegram_notify(self, _is_cfg, mock_notify, mock_cache):
        mock_cache.get.return_value = None
        room = ChatRoom.objects.create(
            customer_name="Juan", customer_email="juan@x.com",
        )
        resp = self.client.post(
            f"/chat/{room.token}/send/", data={"body": "ayuda con netflix"},
        )
        self.assertEqual(resp.status_code, 200)
        mock_notify.assert_called_once()
        text_arg = mock_notify.call_args[0][0]
        self.assertIn("Juan", text_arg)
        self.assertIn("ayuda con netflix", text_arg)
        # Después de notificar, marcamos cache para debounce.
        mock_cache.set.assert_called_once()

    @patch("livechat.telegram_notify.cache")
    @patch("orders.telegram.notify_admin")
    @patch("orders.telegram.is_configured", return_value=True)
    def test_telegram_debounced_by_recent_notification(
        self, _is_cfg, mock_notify, mock_cache,
    ):
        # Cache.get ya devuelve algo → no notificamos.
        mock_cache.get.return_value = True
        room = ChatRoom.objects.create(customer_email="x@y.com")
        self.client.post(
            f"/chat/{room.token}/send/", data={"body": "primer mensaje"},
        )
        self.client.post(
            f"/chat/{room.token}/send/", data={"body": "segundo mensaje"},
        )
        mock_notify.assert_not_called()

    @patch("orders.telegram.is_configured", return_value=False)
    def test_telegram_skipped_when_not_configured(self, _is_cfg):
        room = ChatRoom.objects.create(customer_email="x@y.com")
        # No debe romper aunque no haya bot configurado.
        resp = self.client.post(
            f"/chat/{room.token}/send/", data={"body": "ping"},
        )
        self.assertEqual(resp.status_code, 200)


class PrefillAuthenticatedUserTests(TestCase):
    """Si el cliente está logueado, el widget debe pre-llenar nombre/email."""

    def test_widget_renders_prefill_data_when_authenticated(self):
        user = User.objects.create_user(
            username="luis", email="luis@example.com",
            first_name="Luis", last_name="Perez",
            password="x",
        )
        self.client.force_login(user)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'data-prefill-name="Luis Perez"')
        self.assertContains(resp, 'data-prefill-email="luis@example.com"')

    def test_widget_no_prefill_when_anonymous(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "data-prefill-name=")
        self.assertNotContains(resp, "data-prefill-email=")


class OnlineStatusTagTests(TestCase):
    """`livechat_is_online` y banner online/offline."""

    @patch("livechat.templatetags.livechat.timezone")
    def test_online_at_midday(self, mock_tz):
        mock_tz.localtime.return_value = datetime(2026, 1, 1, 14, 0)
        self.assertTrue(livechat_is_online())

    @patch("livechat.templatetags.livechat.timezone")
    def test_offline_at_3am(self, mock_tz):
        mock_tz.localtime.return_value = datetime(2026, 1, 1, 3, 0)
        self.assertFalse(livechat_is_online())

    @patch("livechat.templatetags.livechat.timezone")
    def test_offline_at_11pm(self, mock_tz):
        mock_tz.localtime.return_value = datetime(2026, 1, 1, 23, 0)
        self.assertFalse(livechat_is_online())

    @patch("livechat.templatetags.livechat.timezone")
    def test_online_at_9am_sharp(self, mock_tz):
        mock_tz.localtime.return_value = datetime(2026, 1, 1, 9, 0)
        self.assertTrue(livechat_is_online())

    @patch("livechat.templatetags.livechat.timezone")
    def test_widget_renders_online_banner(self, mock_tz):
        mock_tz.localtime.return_value = datetime(2026, 1, 1, 14, 0)
        resp = self.client.get("/")
        self.assertContains(resp, "Online · Te respondemos en minutos")
        self.assertContains(resp, 'data-status="online"')

    @patch("livechat.templatetags.livechat.timezone")
    def test_widget_renders_offline_banner(self, mock_tz):
        mock_tz.localtime.return_value = datetime(2026, 1, 1, 3, 0)
        resp = self.client.get("/")
        self.assertContains(resp, "Fuera de horario")
        self.assertContains(resp, 'data-status="offline"')
