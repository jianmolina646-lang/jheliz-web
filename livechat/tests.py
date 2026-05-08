"""Tests del chat en vivo (público + admin)."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .models import ChatMessage, ChatRoom


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
