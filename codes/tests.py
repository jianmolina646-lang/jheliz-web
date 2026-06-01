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

    def test_links_have_html_entities_decoded(self):
        html = (
            "<p>Tu código de inicio de sesión</p>"
            '<a href="https://www.netflix.com/accountaccess?g=1&amp;lkid=X&amp;lnktrk=EVO">'
            "Ver cuenta</a>"
        )
        r = parse_netflix_email("Netflix: Tu código de inicio de sesión", html=html)
        self.assertIn("&lkid=X", r.action_url)
        self.assertNotIn("&amp;", r.action_url)

    def test_unknown_email_is_other(self):
        r = parse_netflix_email("Novedades de Netflix", html="<p>Mira lo nuevo</p>")
        self.assertEqual(r.kind, "other")
        self.assertFalse(r.has_payload)

    def test_password_reset_classification_and_link(self):
        html = (
            "<p>Restablece tu contraseña</p>"
            '<a href="https://www.netflix.com/password?g=1&amp;lkid=Y">'
            "Crear contraseña nueva</a>"
        )
        r = parse_netflix_email("Netflix: Restablece tu contraseña", html=html)
        self.assertEqual(r.kind, "password_reset")
        self.assertIn("/password", r.action_url)
        self.assertNotIn("&amp;", r.action_url)


class CommandMappingTests(TestCase):
    def test_four_commands_mapped_to_kinds(self):
        self.assertEqual(
            bot.COMMAND_KINDS,
            {
                "/codigo": "signin_code",
                "/viaje": "temp_code",
                "/hogar": "household",
                "/clave": "password_reset",
            },
        )

    def test_every_command_kind_has_a_label(self):
        for kind in bot.COMMAND_KINDS.values():
            self.assertIn(kind, bot.KIND_LABELS)


class AdminWelcomeTests(TestCase):
    @mock.patch("codes.bot.send_message")
    def test_admin_is_auto_active_and_no_pending_message(self, msend):
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            client, _ = bot._get_or_create_client("900", "admin", "Admin")
            self.assertTrue(client.is_active)
            bot._send_welcome(client)
        text = msend.call_args[0][1]
        self.assertNotIn("Pasáselo al admin", text)
        self.assertIn("admin", text.lower())

    @mock.patch("codes.bot.send_message")
    def test_regular_client_still_sees_pending_message(self, msend):
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            client, _ = bot._get_or_create_client("123", "user", "User")
            self.assertFalse(client.is_active)
            bot._send_welcome(client)
        text = msend.call_args[0][1]
        self.assertIn("no está activado", text)
        self.assertIn("123", text)  # le muestra su ID para pasárselo al admin


class CmdsHelpTests(TestCase):
    @mock.patch("codes.bot.send_message")
    def test_cmds_admin_shows_admin_commands(self, msend):
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            client, _ = bot._get_or_create_client("900", "admin", "Admin")
            bot._send_commands_help(client)
        text = msend.call_args[0][1]
        self.assertIn("/anuncio", text)
        self.assertIn("/clientes", text)

    @mock.patch("codes.bot.send_message")
    def test_cmds_active_client_shows_only_client_commands(self, msend):
        c = CodeBotClient.objects.create(telegram_chat_id="333", is_active=True)
        AssignedEmail.objects.create(client=c, email="x@gmail.com")
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            bot._send_commands_help(c)
        text = msend.call_args[0][1]
        self.assertIn("/codigo", text)
        self.assertNotIn("/anuncio", text)

    @mock.patch("codes.bot.send_message")
    def test_cmds_inactive_client_gets_activation_message(self, msend):
        c = CodeBotClient.objects.create(telegram_chat_id="444", is_active=False)
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            bot._send_commands_help(c)
        text = msend.call_args[0][1]
        self.assertIn("no está activado", text)


class BroadcastTests(TestCase):
    def setUp(self):
        CodeBotClient.objects.create(telegram_chat_id="111", is_active=True)
        CodeBotClient.objects.create(telegram_chat_id="222", is_active=False)

    @mock.patch("codes.bot.send_message", return_value={"ok": True})
    def test_anuncio_sends_to_all_started_clients_except_admin(self, msend):
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            CodeBotClient.objects.create(telegram_chat_id="900", is_active=True)
            bot._handle_admin_command("900", "/anuncio", "Hola a todos")
        recipients = [c.args[0] for c in msend.call_args_list]
        self.assertIn("111", recipients)
        self.assertIn("222", recipients)
        # El admin no recibe la copia del anuncio, solo el resumen final.
        self.assertEqual(recipients.count("900"), 1)
        self.assertEqual(recipients[-1], "900")
        self.assertIn("Anuncio enviado", msend.call_args_list[-1].args[1])

    @mock.patch("codes.bot.send_message", return_value={"ok": True})
    def test_anuncio_sin_mensaje_muestra_uso(self, msend):
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            bot._handle_admin_command("900", "/anuncio", "")
        text = msend.call_args[0][1]
        self.assertIn("Uso:", text)

    @mock.patch("codes.bot.send_message")
    def test_anuncio_ignored_for_non_admin(self, msend):
        # Un cliente cualquiera manda /anuncio: no debe difundir nada.
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            bot.process_update(
                {
                    "message": {
                        "chat": {"id": 111},
                        "from": {"username": "x"},
                        "text": "/anuncio spam para todos",
                    }
                }
            )
        sent_bodies = [c.args[1] for c in msend.call_args_list]
        self.assertFalse(any("spam para todos" in b for b in sent_bodies))


class AdminCommandTests(TestCase):
    def setUp(self):
        # Cliente registrado en el bot pero sin correos (no está en la web).
        self.cliente = CodeBotClient.objects.create(
            telegram_chat_id="424242", telegram_username="pepe", display_name="Pepe"
        )

    @mock.patch("codes.bot.send_message")
    def test_asignar_crea_correo_y_activa(self, msend):
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            bot._handle_admin_command("900", "/asignar", "424242 NUEVA@Gmail.com")
        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.is_active)
        self.assertEqual(
            list(self.cliente.emails.values_list("email", flat=True)),
            ["nueva@gmail.com"],
        )
        # Avisa al admin y al cliente.
        self.assertEqual(msend.call_count, 2)

    @mock.patch("codes.bot.send_message")
    def test_asignar_por_username(self, _msend):
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            bot._handle_admin_command("900", "/asignar", "@pepe cuenta@gmail.com")
        self.assertTrue(
            self.cliente.emails.filter(email="cuenta@gmail.com").exists()
        )

    @mock.patch("codes.bot.send_message")
    def test_asignar_cliente_inexistente_avisa(self, msend):
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            bot._handle_admin_command("900", "/asignar", "999999 x@gmail.com")
        text = msend.call_args[0][1]
        self.assertIn("No encontré un cliente", text)

    @mock.patch("codes.bot.send_message")
    def test_quitar_borra_correo(self, _msend):
        AssignedEmail.objects.create(client=self.cliente, email="del@gmail.com")
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            bot._handle_admin_command("900", "/quitar", "424242 del@gmail.com")
        self.assertFalse(
            self.cliente.emails.filter(email="del@gmail.com").exists()
        )

    @mock.patch("codes.bot.send_message")
    def test_asignar_correo_invalido(self, msend):
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            bot._handle_admin_command("900", "/asignar", "424242 no-es-correo")
        text = msend.call_args[0][1]
        self.assertIn("no parece un correo válido", text)

    @mock.patch("codes.bot.send_message")
    def test_admin_commands_ignored_for_non_admin(self, msend):
        # Un cliente cualquiera manda /asignar: no se ejecuta como admin.
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            bot.process_update(
                {
                    "message": {
                        "chat": {"id": 424242},
                        "from": {"username": "pepe"},
                        "text": "/asignar 424242 hack@gmail.com",
                    }
                }
            )
        # No se asignó nada (no es admin).
        self.assertFalse(self.cliente.emails.exists())


class CmdCodeTests(TestCase):
    def setUp(self):
        self.client_obj = CodeBotClient.objects.create(
            telegram_chat_id="555", is_active=True
        )
        AssignedEmail.objects.create(client=self.client_obj, email="solo@gmail.com")

    @mock.patch("codes.bot.send_message")
    @mock.patch("codes.bot._deliver_code", return_value="OK")
    def test_single_email_fallback_when_no_arg(self, mdeliver, _msend):
        bot._cmd_code(self.client_obj, "signin_code", "")
        mdeliver.assert_called_once_with(
            self.client_obj, "solo@gmail.com", kind="signin_code"
        )

    @mock.patch("codes.bot.send_message")
    @mock.patch("codes.bot._deliver_code", return_value="OK")
    def test_explicit_email_arg_is_used(self, mdeliver, _msend):
        bot._cmd_code(self.client_obj, "household", "Solo@Gmail.com")
        mdeliver.assert_called_once_with(
            self.client_obj, "solo@gmail.com", kind="household"
        )

    @mock.patch("codes.bot._deliver_code", return_value="OK")
    @mock.patch("codes.bot.send_message")
    def test_multiple_emails_no_arg_shows_picker(self, msend, mdeliver):
        AssignedEmail.objects.create(client=self.client_obj, email="otro@gmail.com")
        bot._cmd_code(self.client_obj, "temp_code", "")
        mdeliver.assert_not_called()
        _args, kwargs = msend.call_args
        self.assertTrue(kwargs.get("buttons"))


class DeliverKindTests(TestCase):
    def setUp(self):
        self.client_obj = CodeBotClient.objects.create(
            telegram_chat_id="777", is_active=True
        )
        AssignedEmail.objects.create(client=self.client_obj, email="mine@gmail.com")

    @mock.patch("codes.bot.imap_reader.is_configured", return_value=True)
    @mock.patch("codes.bot.imap_reader.fetch_latest_for_email", return_value=None)
    def test_kind_is_forwarded_to_imap(self, mfetch, _cfg):
        bot._deliver_code(self.client_obj, "mine@gmail.com", kind="password_reset")
        mfetch.assert_called_once_with("mine@gmail.com", kind="password_reset")

    def test_unassigned_email_says_no_corresponde(self):
        msg = bot._deliver_code(self.client_obj, "ajeno@gmail.com", kind="signin_code")
        self.assertIn("no te corresponde", msg)

    @mock.patch("codes.bot.send_message")
    def test_offer_kinds_rejects_unassigned(self, msend):
        bot._offer_kinds_for_email(self.client_obj, "ajeno@gmail.com")
        text = msend.call_args[0][1]
        self.assertIn("no te corresponde", text)

    @mock.patch("codes.bot.send_message")
    def test_offer_kinds_shows_four_options(self, msend):
        bot._offer_kinds_for_email(self.client_obj, "mine@gmail.com")
        _args, kwargs = msend.call_args
        self.assertEqual(len(kwargs.get("buttons", [])), 4)


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
