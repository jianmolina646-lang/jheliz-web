from unittest import mock

from django.db import IntegrityError
from django.test import TestCase

from codes import bot
from codes.models import AssignedEmail, CodeBotClient
from codes.netflix import NetflixResult, parse_netflix_email


class ModelTests(TestCase):
    def test_email_is_normalized_lowercase(self):
        c = CodeBotClient.objects.create(telegram_chat_id="111")
        e = AssignedEmail.objects.create(client=c, email="  Foo@Gmail.COM ")
        self.assertEqual(e.email, "foo@gmail.com")

    def test_same_email_unique_per_client(self):
        c = CodeBotClient.objects.create(telegram_chat_id="222")
        AssignedEmail.objects.create(client=c, email="a@gmail.com")
        with self.assertRaises(IntegrityError):
            AssignedEmail.objects.create(client=c, email="a@gmail.com")

    def test_same_email_can_belong_to_two_clients(self):
        c1 = CodeBotClient.objects.create(telegram_chat_id="1")
        c2 = CodeBotClient.objects.create(telegram_chat_id="2")
        AssignedEmail.objects.create(client=c1, email="shared@gmail.com")
        AssignedEmail.objects.create(client=c2, email="shared@gmail.com")
        self.assertEqual(AssignedEmail.objects.filter(email="shared@gmail.com").count(), 2)


class NetflixParserTests(TestCase):
    def test_temp_code_classification_and_link(self):
        html = (
            '<p>Tu código de acceso temporal</p>'
            '<a href="https://www.netflix.com/account/travel/verify?nftoken=abc">'
            "Obtener código</a>"
        )
        r = parse_netflix_email("Tu código de acceso temporal", html=html)
        self.assertEqual(r.kind, "temp_code")
        self.assertIn("travel/verify", r.action_url)

    def test_household_classification(self):
        html = (
            "<p>Cómo actualizar tu Hogar con Netflix</p>"
            '<a href="https://www.netflix.com/account/update-primary-location?nftoken=z">'
            "Sí, la envié yo</a>"
        )
        r = parse_netflix_email("Importante: actualizar tu Hogar", html=html)
        self.assertEqual(r.kind, "household")
        self.assertIn("update-primary-location", r.action_url)

    def test_numeric_code_extracted_from_text(self):
        r = parse_netflix_email(
            "Tu código de inicio de sesión",
            text="Tu código es 4821 y vence pronto.",
        )
        self.assertEqual(r.kind, "signin_code")
        self.assertEqual(r.code, "4821")

    def test_unknown_email_is_other(self):
        r = parse_netflix_email("Novedades de Netflix", html="<p>Mira lo nuevo</p>")
        self.assertEqual(r.kind, "other")
        self.assertFalse(r.has_payload)


class DeliverCodeTests(TestCase):
    def setUp(self):
        self.client_obj = CodeBotClient.objects.create(
            telegram_chat_id="999", is_active=True
        )
        AssignedEmail.objects.create(client=self.client_obj, email="mine@gmail.com")

    def test_denies_unassigned_email(self):
        msg = bot._deliver_code(self.client_obj, "other@gmail.com")
        self.assertIn("no está asignado", msg)

    @mock.patch("codes.bot.imap_reader.is_configured", return_value=True)
    @mock.patch("codes.bot.imap_reader.fetch_latest_for_email", return_value=None)
    def test_no_recent_code(self, _fetch, _cfg):
        msg = bot._deliver_code(self.client_obj, "mine@gmail.com")
        self.assertIn("No encontré un código reciente", msg)

    @mock.patch("codes.bot.imap_reader.is_configured", return_value=True)
    def test_delivers_payload(self, _cfg):
        result = NetflixResult(
            kind="temp_code",
            subject="Tu código de acceso temporal",
            action_url="https://www.netflix.com/account/travel/verify?nftoken=x",
        )
        with mock.patch(
            "codes.bot.imap_reader.fetch_latest_for_email", return_value=result
        ):
            msg = bot._deliver_code(self.client_obj, "mine@gmail.com")
        self.assertIn("Abrir en Netflix", msg)
        self.assertIn("netflix.com", msg)
