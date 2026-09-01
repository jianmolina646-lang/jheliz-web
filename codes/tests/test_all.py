from unittest import mock
import json
from pathlib import Path

from django.core.cache import cache
from django.db import IntegrityError
from django.test import TestCase, override_settings

from codes import bot, imap_reader
from codes.models import AssignedEmail, BotState, CodeBotClient, CodeDelivery, DisneyAssignedEmail, DisneyBotClient, DisneyCodeDelivery
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
    def test_anonymized_real_format_samples(self):
        fixture = Path(__file__).parent / "fixtures" / "netflix_samples.json"
        for sample in json.loads(fixture.read_text(encoding="utf-8")):
            with self.subTest(sample=sample["name"]):
                result = parse_netflix_email(
                    sample["subject"], html=sample["html"], text=sample["text"]
                )
                self.assertEqual(result.kind, sample["kind"])
                self.assertEqual(result.code, sample["code"])
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

    def test_numeric_code_uses_html_when_plain_text_is_only_preheader(self):
        r = parse_netflix_email(
            "Tu código de inicio de sesión",
            html="<p>Tu código de inicio de sesión</p><h1>7391</h1>",
            text="Solicitaste iniciar sesión en Netflix.",
        )
        self.assertEqual(r.kind, "signin_code")
        self.assertEqual(r.code, "7391")

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

    def test_new_signin_request_security_alert_is_not_delivered_as_code(self):
        r = parse_netflix_email(
            "Netflix: Nueva solicitud de inicio de sesión",
            html=(
                "<p>Si no fuiste tú, rechaza esta solicitud.</p>"
                '<a href="https://www.netflix.com/denysignin?nftoken=abc">'
                "Rechazar inicio de sesión</a>"
            ),
        )
        self.assertEqual(r.kind, "other")

    def test_new_tv_signin_request_delivers_approval_and_never_rejection(self):
        r = parse_netflix_email(
            "Netflix: Nueva solicitud de inicio de sesión",
            html=(
                "<h1>Aprueba la nueva solicitud de inicio de sesión</h1>"
                "<p>JVC - Smart TV</p>"
                '<a href="https://www.netflix.com/ilum?token=approve">'
                "Aprobar solicitud</a>"
                '<a href="https://www.netflix.com/denysignin?token=deny">'
                "Rechazar solicitud</a>"
            ),
        )
        self.assertEqual(r.kind, "tv_signin")
        self.assertIn("/ilum", r.action_url)
        self.assertNotIn("/denysignin", r.action_url)

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

    def test_signin_code_italian(self):
        # Correo real reenviado: cuenta de Netflix configurada en italiano.
        text = (
            "Asunto: Netflix: il tuo codice di accesso\n"
            "Inserisci questo codice per accedere\n"
            "2056\n"
            "Inserisci il codice qui sopra sul tuo dispositivo per accedere a "
            "Netflix. Il codice scadrà tra 15 minuti."
        )
        r = parse_netflix_email("RV: Netflix: il tuo codice di accesso", text=text)
        self.assertEqual(r.kind, "signin_code")
        self.assertEqual(r.code, "2056")

    def test_temp_code_italian_is_not_signin(self):
        r = parse_netflix_email(
            "Netflix: il tuo codice di accesso temporaneo",
            text="Il tuo codice di accesso temporaneo è 7788. Codice valido 15 minuti.",
        )
        self.assertEqual(r.kind, "temp_code")
        self.assertEqual(r.code, "7788")

    def test_signin_code_portuguese(self):
        r = parse_netflix_email(
            "Netflix: seu código de acesso",
            text="Use este código para entrar\n4471\nO código expira em 15 minutos.",
        )
        self.assertEqual(r.kind, "signin_code")
        self.assertEqual(r.code, "4471")

    def test_signin_code_french(self):
        r = parse_netflix_email(
            "Netflix : ton code de connexion",
            text="Saisis ce code pour te connecter\n8842\nLe code expire dans 15 minutes.",
        )
        self.assertEqual(r.kind, "signin_code")
        self.assertEqual(r.code, "8842")

    def test_unknown_language_falls_back_to_link_path(self):
        # Idioma no cubierto por keywords (ej. turco): clasifica por la ruta
        # del link, que es igual en todos los países.
        html = (
            "<p>Geçici erişim kodun</p>"
            '<a href="https://www.netflix.com/account/travel/verify?nftoken=q">'
            "Kod al</a>"
        )
        r = parse_netflix_email("Netflix gecici erisim kodu", html=html)
        self.assertEqual(r.kind, "temp_code")
        self.assertIn("travel/verify", r.action_url)

    def test_code_on_its_own_line_any_language(self):
        # El número solo en su propia línea se extrae aunque el idioma no
        # tenga la palabra "código"/"code" cerca.
        r = parse_netflix_email(
            "Netflix: il tuo codice di accesso",
            text="Inserisci per accedere:\n\n  591203  \n\nScade tra 15 minuti.",
        )
        self.assertEqual(r.kind, "signin_code")
        self.assertEqual(r.code, "591203")

    def test_tv_signin_classification_and_link(self):
        html = (
            "<p>Inicia sesión en tu TV</p>"
            '<a href="https://www.netflix.com/tv/out/es?nftoken=abc">'
            "Iniciar sesión en la TV</a>"
        )
        r = parse_netflix_email("Es hora de ver Netflix", html=html)
        self.assertEqual(r.kind, "tv_signin")
        self.assertIn("/tv/", r.action_url)

    def test_passwordless_signin_classification_and_link(self):
        html = (
            "<p>Inicia sesión sin una contraseña</p>"
            '<a href="https://www.netflix.com/accountaccess?g=1&amp;lkid=TV">'
            "Enviar enlace de inicio de sesión</a>"
        )
        r = parse_netflix_email(
            "Inicia sesión sin una contraseña",
            html=html,
        )
        self.assertEqual(r.kind, "passwordless_signin")
        self.assertIn("/accountaccess?", r.action_url)
        self.assertNotIn("&amp;", r.action_url)

    def test_passwordless_signin_rejects_lookalike_domain(self):
        html = (
            "<p>Inicia sesión sin una contraseña</p>"
            '<a href="https://netflix.com.attacker.example/accountaccess?token=x">'
            "Iniciar sesión</a>"
        )
        r = parse_netflix_email(
            "Inicia sesión sin una contraseña",
            html=html,
        )
        self.assertEqual(r.kind, "passwordless_signin")
        self.assertEqual(r.action_url, "")

    def test_rejects_lookalike_netflix_domain(self):
        html = (
            "<p>Inicia sesión en tu TV</p>"
            '<a href="https://evilnetflix.com/tv/out?nftoken=steal">Activar</a>'
        )
        r = parse_netflix_email("Inicia sesión en tu TV", html=html)
        self.assertEqual(r.kind, "tv_signin")
        self.assertEqual(r.action_url, "")


class ImapAccountsTests(TestCase):
    def test_internaldate_is_preferred_over_spoofable_date_header(self):
        from datetime import datetime, timezone
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["Date"] = "Mon, 01 Jan 2001 00:00:00 +0000"
        metadata = b'1 (INTERNALDATE "25-Aug-2026 13:30:00 +0000" RFC822 {1})'
        self.assertEqual(
            imap_reader._msg_datetime(msg, metadata),
            datetime(2026, 8, 25, 13, 30, tzinfo=timezone.utc),
        )

    def test_missing_date_is_not_treated_as_new(self):
        from email.message import EmailMessage

        self.assertIsNone(imap_reader._msg_datetime(EmailMessage()))

    @override_settings(
        CODES_IMAP_HOST="proton-bridge.internal",
        CODES_IMAP_USER="corp@jhelizstore.xyz",
        CODES_IMAP_PASSWORD="x",
        CODES_IMAP2_HOST="imap.backup.example",
        CODES_IMAP2_USER="backup@example.com",
        CODES_IMAP2_PASSWORD="y",
    )
    def test_two_accounts_configured(self):
        accounts = imap_reader._accounts()
        self.assertEqual(len(accounts), 2)
        self.assertEqual(accounts[0]["host"], "proton-bridge.internal")
        self.assertEqual(accounts[1]["host"], "imap.backup.example")
        self.assertTrue(imap_reader.is_configured())

    @override_settings(
        CODES_IMAP_HOST="proton-bridge.internal",
        CODES_IMAP_USER="corp@jhelizstore.xyz",
        CODES_IMAP_PASSWORD="x",
        CODES_IMAP2_HOST="imap.backup.example",
        CODES_IMAP2_USER="",
        CODES_IMAP2_PASSWORD="",
    )
    def test_secondary_without_credentials_is_skipped(self):
        accounts = imap_reader._accounts()
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["user"], "corp@jhelizstore.xyz")

    @override_settings(
        CODES_IMAP_HOST="proton-bridge.internal",
        CODES_IMAP_USER="g@gmail.com",
        CODES_IMAP_PASSWORD="x",
        CODES_IMAP2_HOST="imap.backup.example",
        CODES_IMAP2_USER="h@host.com",
        CODES_IMAP2_PASSWORD="y",
    )
    def test_fetch_returns_newest_across_mailboxes(self):
        from datetime import datetime, timezone

        old = NetflixResult(kind="signin_code", code="1111")
        new = NetflixResult(kind="signin_code", code="2222")

        def fake_search(account, *args, **kwargs):
            if account["host"] == "proton-bridge.internal":
                return [(datetime(2026, 1, 1, tzinfo=timezone.utc), old)]
            return [(datetime(2026, 1, 2, tzinfo=timezone.utc), new)]

        with mock.patch("codes.imap_reader._search_account", side_effect=fake_search):
            r = imap_reader.fetch_latest_for_email("cliente@gmail.com", kind="signin_code")
        self.assertEqual(r.code, "2222")

    @override_settings(
        CODES_IMAP_HOST="proton-bridge.internal",
        CODES_IMAP_USER="g@gmail.com",
        CODES_IMAP_PASSWORD="x",
        CODES_IMAP2_HOST="imap.backup.example",
        CODES_IMAP2_USER="h@host.com",
        CODES_IMAP2_PASSWORD="y",
    )
    def test_one_mailbox_failing_still_returns_result(self):
        from datetime import datetime, timezone

        res = NetflixResult(kind="signin_code", code="3333")

        def fake_search(account, *args, **kwargs):
            if account["host"] == "proton-bridge.internal":
                raise OSError("gmail caído")
            return [(datetime(2026, 1, 2, tzinfo=timezone.utc), res)]

        with mock.patch("codes.imap_reader._search_account", side_effect=fake_search):
            r = imap_reader.fetch_latest_for_email("cliente@gmail.com", kind="signin_code")
        self.assertEqual(r.code, "3333")


class CommandMappingTests(TestCase):
    def test_commands_mapped_to_kinds(self):
        self.assertEqual(
            bot.COMMAND_KINDS,
            {
                "/codigo": "signin_code",
                "/viaje": "temp_code",
                "/hogar": "household",
                "/clave": "password_reset",
                "/tv": "tv_signin",
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
        self.assertIn("/limite", text)

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
    def test_admin_can_set_and_read_daily_limit(self, msend):
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            bot._handle_admin_command("900", "/limite", "5000")
            self.assertEqual(bot._daily_limit(), 5000)
            bot._handle_admin_command("900", "/limite", "")
        self.assertIn("5,000", msend.call_args_list[-1].args[1])

    @mock.patch("codes.bot.send_message")
    def test_admin_can_disable_daily_limit(self, msend):
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            bot._handle_admin_command("900", "/limite", "0")
            self.assertEqual(bot._daily_limit(), 0)
            bot._handle_admin_command("900", "/limite", "")
        self.assertIn("Sin límite", msend.call_args_list[-1].args[1])

    @mock.patch("codes.bot.send_message")
    def test_non_admin_cannot_change_daily_limit(self, _msend):
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            bot.process_update(
                {
                    "message": {
                        "chat": {"id": 424242},
                        "from": {"username": "pepe"},
                        "text": "/limite 5000",
                    }
                }
            )
        self.assertFalse(BotState.objects.filter(pk=1).exists())

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


class ActivateClientTests(TestCase):
    def setUp(self):
        self.cliente = CodeBotClient.objects.create(
            telegram_chat_id="424242", telegram_username="pepe", display_name="Pepe"
        )

    @mock.patch("codes.bot.send_message")
    def test_activar_sin_asignar_correo(self, msend):
        self.assertFalse(self.cliente.is_active)
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            bot._handle_admin_command("900", "/activar", "424242")
        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.is_active)
        self.assertFalse(self.cliente.emails.exists())
        # Avisa al admin y al cliente.
        self.assertEqual(msend.call_count, 2)

    @mock.patch("codes.bot.send_message")
    def test_activar_por_username(self, _msend):
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            bot._handle_admin_command("900", "/activar", "@pepe")
        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.is_active)

    @mock.patch("codes.bot.send_message")
    def test_desactivar_pausa_acceso(self, _msend):
        self.cliente.is_active = True
        self.cliente.save(update_fields=["is_active"])
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            bot._handle_admin_command("900", "/desactivar", "424242")
        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.is_active)

    @mock.patch("codes.bot.send_message")
    def test_activar_sin_token_muestra_uso(self, msend):
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            bot._handle_admin_command("900", "/activar", "")
        self.assertIn("Uso:", msend.call_args[0][1])

    @mock.patch("codes.bot.send_message")
    def test_activar_ignored_for_non_admin(self, _msend):
        with self.settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900"):
            bot.process_update(
                {
                    "message": {
                        "chat": {"id": 424242},
                        "from": {"username": "pepe"},
                        "text": "/activar 424242",
                    }
                }
            )
        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.is_active)


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

    @mock.patch("codes.bot.send_message")
    @mock.patch("codes.bot._deliver_code", return_value="OK")
    def test_direct_command_accepts_newline_and_escaped_at(self, mdeliver, _msend):
        bot._handle_message(
            {
                "message": {
                    "chat": {"id": 555},
                    "from": {"username": "cliente"},
                    "text": "/codigo\nsolo\\@gmail.com",
                }
            }
        )
        mdeliver.assert_called_once_with(
            self.client_obj, "solo@gmail.com", kind="signin_code"
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
        cache.clear()
        self.client_obj = CodeBotClient.objects.create(
            telegram_chat_id="777", is_active=True
        )
        AssignedEmail.objects.create(client=self.client_obj, email="mine@gmail.com")

    @mock.patch("codes.bot.imap_reader.is_configured", return_value=True)
    @mock.patch("codes.bot.imap_reader.fetch_latest_for_email", return_value=None)
    def test_kind_is_forwarded_without_fallback_to_another_type(self, mfetch, _cfg):
        bot._deliver_code(self.client_obj, "mine@gmail.com", kind="password_reset")
        self.assertEqual(
            mfetch.call_args_list,
            [mock.call("mine@gmail.com", kind="password_reset")],
        )

    def test_unassigned_email_says_no_corresponde(self):
        msg = bot._deliver_code(self.client_obj, "ajeno@gmail.com", kind="signin_code")
        self.assertIn("no te corresponde", msg)

    @mock.patch("codes.bot.send_message")
    def test_offer_kinds_rejects_unassigned(self, msend):
        bot._offer_kinds_for_email(self.client_obj, "ajeno@gmail.com")
        text = msend.call_args[0][1]
        self.assertIn("no te corresponde", text)

    @mock.patch("codes.bot.send_message")
    def test_offer_kinds_shows_all_options(self, msend):
        bot._offer_kinds_for_email(self.client_obj, "mine@gmail.com")
        _args, kwargs = msend.call_args
        # Una fila por acción y una fila final para volver.
        self.assertEqual(len(kwargs.get("buttons", [])), len(bot.COMMAND_KINDS) + 1)


class SearchAssignedEmailsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client_obj = CodeBotClient.objects.create(
            telegram_chat_id="778", is_active=True
        )
        for email in (
            "ana.netflix@gmail.com",
            "ventas.netflix@gmail.com",
            "cliente@outlook.com",
        ):
            AssignedEmail.objects.create(client=self.client_obj, email=email)

    @mock.patch("codes.bot.send_message")
    def test_search_without_query_shows_usage(self, msend):
        bot._cmd_search(self.client_obj, "")
        self.assertIn("/codigo", msend.call_args.args[1])
        self.assertNotIn("/buscar", msend.call_args.args[1])

    @mock.patch("codes.bot._offer_kinds_for_email")
    def test_single_match_opens_actions(self, moffer):
        bot._cmd_search(self.client_obj, "cliente@outlook")
        moffer.assert_called_once_with(self.client_obj, "cliente@outlook.com")

    @mock.patch("codes.bot.send_message")
    def test_multiple_matches_show_only_matching_buttons(self, msend):
        bot._cmd_search(self.client_obj, "netflix")
        buttons = msend.call_args.kwargs["buttons"]
        labels = [row[0]["text"] for row in buttons]
        self.assertEqual(len(labels), 2)
        self.assertTrue(all("•" in label for label in labels))
        self.assertNotIn("ana.netflix@gmail.com", labels)
        self.assertTrue(
            all(
                row[0]["icon_custom_emoji_id"] == "5249245270381716113"
                for row in buttons
            )
        )

    @mock.patch("codes.bot.send_message")
    def test_search_buttons_keep_indices_from_full_assigned_list(self, msend):
        bot._cmd_search(self.client_obj, "outlook")
        # Una sola coincidencia abre las acciones directamente.
        msend.assert_called()
        action_buttons = msend.call_args.kwargs["buttons"]
        self.assertTrue(
            all(
                row[0]["callback_data"].endswith(":1")
                for row in action_buttons[:-1]
            )
        )
        self.assertEqual(action_buttons[-1][0]["callback_data"], "back:emails")

    @mock.patch("codes.bot.send_message")
    def test_large_mailbox_uses_search_instead_of_huge_button_list(self, msend):
        for idx in range(20):
            AssignedEmail.objects.create(
                client=self.client_obj, email=f"extra{idx:02d}@gmail.com"
            )
        bot._send_email_menu(self.client_obj)
        self.assertIn("/codigo", msend.call_args.args[1])
        self.assertNotIn("/buscar", msend.call_args.args[1])
        self.assertIsNone(msend.call_args.kwargs.get("buttons"))

    @mock.patch("codes.bot.send_message")
    def test_welcome_does_not_send_automatic_email_list(self, msend):
        bot._send_welcome(self.client_obj)
        self.assertEqual(msend.call_count, 1)
        self.assertNotIn("Tus correos:", msend.call_args.args[1])

    def test_email_is_masked_for_customer_ui(self):
        self.assertEqual(
            bot._mask_email("barenkaren02@gmail.com"),
            "bar•••••••02@gmail.com",
        )

    @mock.patch("codes.bot.send_message")
    def test_large_mailbox_shows_recent_accounts(self, msend):
        from codes.models import CodeDelivery

        for idx in range(12):
            AssignedEmail.objects.create(
                client=self.client_obj, email=f"large{idx:02d}@gmail.com"
            )
        CodeDelivery.objects.create(
            client=self.client_obj, email="cliente@outlook.com", found=True
        )
        bot._send_email_menu(self.client_obj)
        self.assertTrue(msend.call_args.kwargs.get("buttons"))
        button_text = msend.call_args.kwargs["buttons"][0][0]["text"]
        self.assertIn("•", button_text)


class CallbackNavigationTests(TestCase):
    def setUp(self):
        self.client_obj = CodeBotClient.objects.create(
            telegram_chat_id="779", is_active=True
        )
        AssignedEmail.objects.create(
            client=self.client_obj, email="cliente@gmail.com"
        )

    @mock.patch("codes.bot.edit_message")
    @mock.patch("codes.bot.answer_callback_query")
    def test_pick_edits_existing_message(self, _answer, medit):
        bot._handle_callback(
            {
                "callback_query": {
                    "id": "cq1",
                    "from": {"id": 779},
                    "data": "pick:0",
                    "message": {"message_id": 55, "chat": {"id": 779}},
                }
            }
        )
        self.assertEqual(medit.call_args.args[:2], (779, 55))
        self.assertIn("•", medit.call_args.args[2])
        self.assertTrue(medit.call_args.kwargs["buttons"])

    @mock.patch("codes.bot.edit_message")
    @mock.patch("codes.bot.answer_callback_query")
    def test_back_edits_selector_instead_of_sending_new_message(self, _answer, medit):
        bot._handle_callback(
            {
                "callback_query": {
                    "id": "cq2",
                    "from": {"id": 779},
                    "data": "back:emails",
                    "message": {"message_id": 56, "chat": {"id": 779}},
                }
            }
        )
        self.assertEqual(medit.call_args.args[:2], (779, 56))
        self.assertIn("/codigo", medit.call_args.args[2])
        self.assertNotIn("/buscar", medit.call_args.args[2])


class DeliverCodeTests(TestCase):
    def setUp(self):
        cache.clear()
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


@override_settings(
    CODES_COOLDOWN_SECONDS=6,
    CODES_RESULT_CACHE_SECONDS=45,
    TELEGRAM_CODES_ADMIN_CHAT_ID="900",
)
class EfficiencyTests(TestCase):
    """Mejoras de eficiencia: caché de resultados, anti-spam y acceso correcto."""

    def setUp(self):
        cache.clear()
        self.client_obj = CodeBotClient.objects.create(
            telegram_chat_id="111", is_active=True
        )
        AssignedEmail.objects.create(client=self.client_obj, email="mine@gmail.com")

    @mock.patch("codes.bot.imap_reader.is_configured", return_value=True)
    def test_result_is_cached_second_call_skips_imap(self, _cfg):
        result = NetflixResult(
            kind="signin_code",
            subject="Tu código de inicio de sesión",
            code="1234",
        )
        with mock.patch(
            "codes.bot.imap_reader.fetch_latest_for_email", return_value=result
        ) as mfetch:
            first = bot._deliver_code(self.client_obj, "mine@gmail.com", kind="signin_code")
            second = bot._deliver_code(self.client_obj, "mine@gmail.com", kind="signin_code")
        # La segunda vez NO vuelve a leer Gmail: usa el caché.
        self.assertEqual(mfetch.call_count, 1)
        self.assertEqual(first, second)
        self.assertIn("1234", second)

    @mock.patch("codes.bot.imap_reader.is_configured", return_value=True)
    @mock.patch("codes.bot.imap_reader.fetch_latest_for_email", return_value=None)
    def test_cooldown_blocks_rapid_second_request(self, _fetch, _cfg):
        # Primer pedido (sin payload): consume el "permiso" del cooldown.
        bot._deliver_code(self.client_obj, "mine@gmail.com", kind="signin_code")
        # Segundo pedido inmediato de OTRO tipo (no cacheado) → frenado.
        msg = bot._deliver_code(self.client_obj, "mine@gmail.com", kind="household")
        self.assertIn("Esperá unos segundos", msg)

    @mock.patch("codes.bot.imap_reader.is_configured", return_value=True)
    @mock.patch("codes.bot.imap_reader.fetch_latest_for_email", return_value=None)
    def test_admin_is_exempt_from_cooldown(self, _fetch, _cfg):
        admin = CodeBotClient.objects.create(telegram_chat_id="900", is_active=True)
        AssignedEmail.objects.create(client=admin, email="mine@gmail.com")
        bot._deliver_code(admin, "mine@gmail.com", kind="signin_code")
        msg = bot._deliver_code(admin, "mine@gmail.com", kind="household")
        self.assertNotIn("Esperá unos segundos", msg)

    @mock.patch("codes.bot.imap_reader.is_configured", return_value=True)
    @mock.patch("codes.bot.imap_reader.fetch_latest_for_email", return_value=None)
    def test_travel_not_found_explains_how_to_generate_email(self, _fetch, _cfg):
        msg = bot._deliver_code(self.client_obj, "mine@gmail.com", kind="temp_code")
        self.assertIn("Generá el correo desde Netflix", msg)
        self.assertIn("volvé a pedirlo en un minuto", msg)

    @mock.patch("codes.bot.imap_reader.is_configured", return_value=True)
    @mock.patch("codes.bot.imap_reader.fetch_latest_for_email", return_value=None)
    def test_household_not_found_explains_how_to_generate_email(self, _fetch, _cfg):
        msg = bot._deliver_code(self.client_obj, "mine@gmail.com", kind="household")
        self.assertIn("Generá el correo desde Netflix", msg)
        self.assertIn("volvé a pedirlo en un minuto", msg)

    @mock.patch("codes.bot.imap_reader.is_configured", return_value=True)
    def test_imap_retried_once_on_error(self, _cfg):
        with mock.patch("codes.bot.time.sleep"), mock.patch(
            "codes.bot.imap_reader.fetch_latest_for_email",
            side_effect=OSError("gmail lento"),
        ) as mfetch:
            msg = bot._deliver_code(self.client_obj, "mine@gmail.com", kind="signin_code")
        self.assertEqual(mfetch.call_count, 2)
        self.assertIn("Hubo un problema", msg)


class BotStateOffsetTests(TestCase):
    def test_offset_defaults_to_zero_and_persists(self):
        self.assertEqual(BotState.get_offset(), 0)
        BotState.set_offset(42)
        self.assertEqual(BotState.get_offset(), 42)
        # Idempotente: siempre fila única (pk=1).
        BotState.set_offset(100)
        self.assertEqual(BotState.objects.count(), 1)
        self.assertEqual(BotState.get_offset(), 100)


class DisneyParserTests(TestCase):
    def test_signin_code_from_text_es(self):
        from codes.disney import parse_disney_email

        r = parse_disney_email(
            "Tu código de acceso único para Disney+",
            text="Tu código de acceso es 123456. Vence pronto.",
        )
        self.assertEqual(r.kind, "signin_code")
        self.assertEqual(r.code, "123456")
        self.assertTrue(r.has_payload)

    def test_signin_code_from_html_en(self):
        from codes.disney import parse_disney_email

        html = "<p>Your one-time passcode is</p><h1>456789</h1><p>It expires soon.</p>"
        r = parse_disney_email("Your Disney+ verification code", html=html)
        self.assertEqual(r.kind, "signin_code")
        self.assertEqual(r.code, "456789")

    def test_prefers_six_digit_near_keyword(self):
        from codes.disney import parse_disney_email

        r = parse_disney_email(
            "Código de verificación",
            text="Pedido 4821. Tu código de verificación es 654321.",
        )
        self.assertEqual(r.code, "654321")

    def test_other_email_is_ignored(self):
        from codes.disney import parse_disney_email

        r = parse_disney_email("Novedades de Disney+", html="<p>Mirá los estrenos</p>")
        self.assertEqual(r.kind, "other")
        self.assertFalse(r.has_payload)
        self.assertEqual(r.code, "")

    def test_ignores_css_color_and_footer_number(self):
        """Caso real Disney+: el color CSS #707070 y el 'Registered No.' del pie
        no deben confundirse con el código; gana el OTP visible real."""
        from codes.disney import parse_disney_email

        html = (
            "<html><head><style>a { color: #707070; } "
            ".btn { background:#252526; }</style></head><body>"
            "<p>Here\u2019s your one-time passcode for Disney+</p>"
            "<table><tr><td>137657</td></tr></table>"
            "<p>associated with your MyDisney account. "
            "It will expire in 15 minutes.</p>"
            "<footer>The Walt Disney Company Limited, 3 Queen Caroline Street, "
            "Hammersmith, London W6 9PE, United Kingdom. Registered No. 530051. "
            "All information \u00a9 Disney.</footer></body></html>"
        )
        r = parse_disney_email("Your one-time passcode for Disney+", html=html)
        self.assertEqual(r.kind, "signin_code")
        self.assertEqual(r.code, "137657")

    def test_uses_html_code_when_text_is_only_preheader(self):
        """El text/plain de Disney+ suele ser un preheader sin el código; el
        código vive en el HTML y debe extraerse igual."""
        from codes.disney import parse_disney_email

        r = parse_disney_email(
            "Your one-time passcode for Disney+",
            html="<p>Your passcode</p><h1>246802</h1><p>expires in 15 minutes</p>",
            text="Here's your one-time passcode for Disney+",
        )
        self.assertEqual(r.kind, "signin_code")
        self.assertEqual(r.code, "246802")


class DisneyBotMappingTests(TestCase):
    def test_single_command_and_service(self):
        from codes import disney_bot

        self.assertEqual(disney_bot.SIGNIN_KIND, "signin_code")
        self.assertEqual(disney_bot.SERVICE, "disney")
        self.assertEqual(disney_bot.BOT_STATE_PK, 2)

    def test_disney_specific_premium_emoji_ids_are_rendered(self):
        from codes import disney_bot

        rendered = disney_bot._render_disney_emojis(
            "{DISNEY_CONTROL} {DISNEY_EXPIRY} {DISNEY_TEAM}"
        )
        self.assertIn('emoji-id="5008435245893026844"', rendered)
        self.assertIn('emoji-id="4956611513369494230"', rendered)
        self.assertIn('emoji-id="5258362837411045098"', rendered)

    @mock.patch("codes.disney_bot.send_message")
    @mock.patch("codes.disney_bot._deliver_code", return_value="OK")
    def test_single_email_fallback_when_no_arg(self, mdeliver, _msend):
        from codes import disney_bot

        c = DisneyBotClient.objects.create(telegram_chat_id="555", is_active=True)
        DisneyAssignedEmail.objects.create(client=c, email="solo@gmail.com")
        disney_bot._cmd_code(c, "")
        mdeliver.assert_called_once_with(c, "solo@gmail.com")

    @mock.patch("codes.disney_bot.send_message")
    @mock.patch("codes.disney_bot._deliver_code", return_value="OK")
    def test_multiple_emails_no_arg_shows_picker(self, mdeliver, msend):
        from codes import disney_bot

        c = DisneyBotClient.objects.create(telegram_chat_id="556", is_active=True)
        DisneyAssignedEmail.objects.create(client=c, email="a@gmail.com")
        DisneyAssignedEmail.objects.create(client=c, email="b@gmail.com")
        disney_bot._cmd_code(c, "")
        mdeliver.assert_not_called()
        _args, kwargs = msend.call_args
        self.assertTrue(kwargs.get("buttons"))

    def test_deliver_blocks_unassigned_email(self):
        from codes import disney_bot

        c = DisneyBotClient.objects.create(telegram_chat_id="557", is_active=True)
        DisneyAssignedEmail.objects.create(client=c, email="mine@gmail.com")
        msg = disney_bot._deliver_code(c, "ajeno@gmail.com")
        self.assertIn("no te corresponde", msg)

    @mock.patch("codes.disney_bot.imap_reader.is_configured", return_value=True)
    @mock.patch("codes.disney_bot.imap_reader.fetch_latest_for_email", return_value=None)
    def test_deliver_uses_disney_service_and_signin_kind(self, mfetch, _cfg):
        from codes import disney_bot

        c = DisneyBotClient.objects.create(telegram_chat_id="558", is_active=True)
        DisneyAssignedEmail.objects.create(client=c, email="mine@gmail.com")
        disney_bot._deliver_code(c, "mine@gmail.com")
        mfetch.assert_called_once_with(
            "mine@gmail.com", kind="signin_code", service="disney"
        )

    @mock.patch("codes.disney_bot.send_message")
    def test_admin_asignar_activates_and_assigns(self, msend):
        from codes import disney_bot

        cliente = DisneyBotClient.objects.create(
            telegram_chat_id="424243", telegram_username="ana"
        )
        with self.settings(TELEGRAM_DISNEY_ADMIN_CHAT_ID="900"):
            disney_bot._handle_admin_command("900", "/asignar", "424243 NUEVA@Gmail.com")
        cliente.refresh_from_db()
        self.assertTrue(cliente.is_active)
        self.assertEqual(
            list(cliente.emails.values_list("email", flat=True)), ["nueva@gmail.com"]
        )

    @mock.patch("codes.disney_bot.imap_reader.is_configured", return_value=True)
    @mock.patch("codes.disney_bot.imap_reader.fetch_latest_for_email")
    def test_same_code_is_not_delivered_twice(self, mfetch, _cfg):
        from codes import disney_bot
        from codes.disney import DisneyResult
        mfetch.return_value = DisneyResult(kind="signin_code", code="123456")
        client = DisneyBotClient.objects.create(telegram_chat_id="601", is_active=True)
        DisneyAssignedEmail.objects.create(client=client, email="disney@example.com")
        self.assertIn("123456", disney_bot._deliver_code(client, "disney@example.com"))
        self.assertIn("ya fue entregado", disney_bot._deliver_code(client, "disney@example.com"))
        self.assertEqual(DisneyCodeDelivery.objects.filter(found=True).count(), 1)


class BotStatePerBotOffsetTests(TestCase):
    def test_offsets_are_independent_per_pk(self):
        BotState.set_offset(10, pk=1)
        BotState.set_offset(20, pk=2)
        self.assertEqual(BotState.get_offset(pk=1), 10)
        self.assertEqual(BotState.get_offset(pk=2), 20)
        self.assertEqual(BotState.objects.count(), 2)


class TvActivationLinkTests(TestCase):
    """El /tv debe incluir la página de activación de la TV."""

    def test_format_result_tv_includes_activation_page(self):
        from codes import bot
        from codes.netflix import NetflixResult

        msg = bot._format_result(
            "cli@x.com", NetflixResult(kind="tv_signin", code="1234")
        )
        self.assertIn(bot.NETFLIX_TV_ACTIVATION_URL, msg)
        self.assertIn("1234", msg)

    def test_format_result_other_kinds_no_activation_page(self):
        from codes import bot
        from codes.netflix import NetflixResult

        msg = bot._format_result(
            "cli@x.com", NetflixResult(kind="signin_code", code="1234")
        )
        self.assertNotIn(bot.NETFLIX_TV_ACTIVATION_URL, msg)


class TvDirectCommandTests(TestCase):
    """El /tv responde directo con la página de activación, sin leer correos."""

    def setUp(self):
        self.client_obj = CodeBotClient.objects.create(
            telegram_chat_id="777", is_active=True
        )

    @mock.patch("codes.bot.send_message")
    @mock.patch("codes.bot._deliver_code", return_value="OK")
    def test_cmd_tv_sends_activation_page_without_imap(self, mdeliver, msend):
        bot._cmd_tv(self.client_obj)
        mdeliver.assert_not_called()
        args, _ = msend.call_args
        self.assertIn(bot.NETFLIX_TV_ACTIVATION_URL, args[1])

    @mock.patch("codes.bot.send_message")
    @mock.patch("codes.bot._send_welcome")
    def test_cmd_tv_inactive_client_gets_welcome(self, mwelcome, msend):
        self.client_obj.is_active = False
        bot._cmd_tv(self.client_obj)
        mwelcome.assert_called_once()
        msend.assert_not_called()


class TvEmailLinkCommandTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client_obj = CodeBotClient.objects.create(
            telegram_chat_id="780", is_active=True
        )
        AssignedEmail.objects.create(
            client=self.client_obj, email="cliente@gmail.com"
        )

    @mock.patch("codes.bot.send_message")
    @mock.patch("codes.bot._deliver_code")
    def test_explicit_email_requires_confirmation_before_imap(self, mdeliver, msend):
        bot._cmd_tv_email(self.client_obj, "Cliente@Gmail.com")
        mdeliver.assert_not_called()
        self.assertIn("Confirmar activación", msend.call_args.args[1])
        buttons = msend.call_args.kwargs["buttons"]
        self.assertEqual(buttons[0][0]["callback_data"], "tvconfirm:0")

    @mock.patch("codes.bot.send_message")
    @mock.patch("codes.bot._deliver_code")
    def test_single_account_can_omit_email(self, mdeliver, msend):
        bot._cmd_tv_email(self.client_obj, "")
        mdeliver.assert_not_called()
        self.assertIn("Confirmar activación", msend.call_args.args[1])

    @mock.patch("codes.bot.send_message")
    @mock.patch("codes.bot._deliver_code")
    def test_multiple_accounts_show_specific_selector(self, mdeliver, msend):
        AssignedEmail.objects.create(
            client=self.client_obj, email="segunda@outlook.com"
        )
        bot._cmd_tv_email(self.client_obj, "")
        mdeliver.assert_not_called()
        buttons = msend.call_args.kwargs["buttons"]
        self.assertTrue(
            all(
                row[0]["callback_data"].startswith("tvmail:")
                for row in buttons
            )
        )
        self.assertTrue(
            all(
                row[0]["icon_custom_emoji_id"] == "5222102644734056755"
                for row in buttons
            )
        )

    @mock.patch("codes.bot.send_message")
    def test_tv_command_remains_general_tv8_flow(self, msend):
        bot._cmd_tv(self.client_obj)
        self.assertIn(bot.NETFLIX_TV_ACTIVATION_URL, msend.call_args.args[1])

    @mock.patch("codes.bot._schedule_sensitive_deletion")
    @mock.patch("codes.bot.edit_message")
    @mock.patch("codes.bot.answer_callback_query")
    @mock.patch("codes.bot._deliver_code", return_value="ENLACE")
    def test_confirm_callback_delivers_and_schedules_deletion(
        self, mdeliver, _answer, medit, mschedule
    ):
        bot._handle_callback(
            {
                "callback_query": {
                    "id": "tv-confirm",
                    "from": {"id": 780},
                    "data": "tvconfirm:0",
                    "message": {"message_id": 77, "chat": {"id": 780}},
                }
            }
        )
        mdeliver.assert_called_once_with(
            self.client_obj,
            "cliente@gmail.com",
            kind="passwordless_signin",
        )
        self.assertEqual(medit.call_args.args[2], "ENLACE")
        mschedule.assert_called_once_with(
            780,
            send_result=medit.return_value,
            message_id=77,
        )

    @mock.patch("codes.bot.imap_reader.is_configured", return_value=True)
    @mock.patch("codes.bot.imap_reader.fetch_latest_for_email")
    def test_tv_email_accepts_tv_signin_email(self, mfetch, _configured):
        mfetch.return_value = NetflixResult(
            kind="tv_signin",
            action_url="https://www.netflix.com/tv/out/es?nftoken=abc",
        )
        message = bot._deliver_code(
            self.client_obj, "cliente@gmail.com", kind="passwordless_signin"
        )
        self.assertIn("nftoken=abc", message)
        mfetch.assert_called_once_with(
            "cliente@gmail.com",
            kind=("passwordless_signin", "tv_signin"),
        )


class SecurityFeatureTests(TestCase):
    """Vencimiento, límite diario, auditoría y alertas al admin."""

    def setUp(self):
        cache.clear()
        self.client_obj = CodeBotClient.objects.create(
            telegram_chat_id="888", is_active=True
        )
        AssignedEmail.objects.create(client=self.client_obj, email="mio@gmail.com")

    @mock.patch("codes.bot.imap_reader.is_configured", return_value=True)
    @mock.patch("codes.bot.imap_reader.fetch_latest_for_email")
    def test_same_payload_is_not_delivered_twice(self, mfetch, _configured):
        mfetch.return_value = NetflixResult(kind="signin_code", code="4321")
        first = bot._deliver_code(self.client_obj, "mio@gmail.com", kind="signin_code")
        cache.clear()
        second = bot._deliver_code(self.client_obj, "mio@gmail.com", kind="signin_code")
        self.assertIn("4321", first)
        self.assertIn("ya fue entregado", second)
        duplicate = CodeDelivery.objects.get(duplicate=True)
        self.assertFalse(duplicate.found)
        self.assertEqual(len(duplicate.payload_fingerprint), 64)

    @mock.patch("codes.bot.imap_reader.health_check", return_value=[{"ok": True}])
    @mock.patch("codes.bot.send_message")
    def test_admin_diagnostic_contains_safe_status(self, msend, _health):
        bot._admin_diagnostics("900")
        message = msend.call_args.args[1]
        self.assertIn("IMAP Proton: OK", message)
        self.assertNotIn("password", message.lower())

    @mock.patch("codes.bot.send_message")
    def test_admin_metrics_reports_kinds(self, msend):
        CodeDelivery.objects.create(
            client=self.client_obj, email="mio@gmail.com", kind="signin_code", found=True
        )
        bot._admin_metrics("900")
        self.assertIn("Código de inicio", msend.call_args.args[1])

    def test_expired_client_has_no_access(self):
        from django.utils import timezone
        from datetime import timedelta

        self.client_obj.expires_at = timezone.now() - timedelta(days=1)
        self.client_obj.save()
        self.assertTrue(self.client_obj.is_expired)
        self.assertFalse(self.client_obj.has_access)
        msg = bot._deliver_code(self.client_obj, "mio@gmail.com")
        self.assertIn("venció", msg)

    def test_future_expiry_keeps_access(self):
        from django.utils import timezone
        from datetime import timedelta

        self.client_obj.expires_at = timezone.now() + timedelta(days=30)
        self.client_obj.save()
        self.assertTrue(self.client_obj.has_access)

    @mock.patch("codes.bot.send_message")
    def test_unassigned_email_alerts_admin(self, msend):
        from codes.models import CodeDelivery

        with mock.patch("codes.bot._admin_chat_id", return_value="999"):
            msg = bot._deliver_code(self.client_obj, "ajeno@gmail.com")
        self.assertIn("no está asignado", msg)
        # Alerta enviada al admin
        self.assertTrue(
            any(c.args[0] == "999" for c in msend.call_args_list)
        )
        self.assertEqual(CodeDelivery.objects.count(), 0)

    @mock.patch("codes.bot.imap_reader.is_configured", return_value=True)
    @mock.patch("codes.bot.imap_reader.fetch_latest_for_email")
    def test_delivery_is_logged(self, mfetch, _mconf):
        from codes.models import CodeDelivery
        from codes.netflix import NetflixResult

        mfetch.return_value = NetflixResult(kind="signin_code", code="4321")
        msg = bot._deliver_code(self.client_obj, "mio@gmail.com", kind="signin_code")
        self.assertIn("4321", msg)
        d = CodeDelivery.objects.get()
        self.assertTrue(d.found)
        self.assertEqual(d.email, "mio@gmail.com")

    @mock.patch("codes.bot.send_message")
    def test_daily_limit_blocks(self, msend):
        from codes.models import CodeDelivery

        with self.settings(CODES_DAILY_LIMIT=2):
            CodeDelivery.objects.create(client=self.client_obj, email="mio@gmail.com", found=True)
            CodeDelivery.objects.create(client=self.client_obj, email="mio@gmail.com", found=True)
            msg = bot._deliver_code(self.client_obj, "mio@gmail.com")
        self.assertIn("límite", msg)

    @mock.patch("codes.bot.imap_reader.is_configured", return_value=True)
    @mock.patch("codes.bot.imap_reader.fetch_latest_for_email")
    def test_zero_daily_limit_never_blocks_assigned_email(self, mfetch, _mconf):
        from codes.models import BotState, CodeDelivery
        from codes.netflix import NetflixResult

        BotState.objects.update_or_create(pk=1, defaults={"daily_limit": 0})
        for _ in range(25):
            CodeDelivery.objects.create(
                client=self.client_obj, email="mio@gmail.com", found=True
            )
        mfetch.return_value = NetflixResult(kind="signin_code", code="4321")
        msg = bot._deliver_code(self.client_obj, "mio@gmail.com", kind="signin_code")
        self.assertIn("4321", msg)


    @mock.patch("codes.bot.send_message")
    def test_three_foreign_attempts_apply_temporary_block(self, _msend):
        with self.settings(
            CODES_FOREIGN_ATTEMPT_LIMIT=3,
            CODES_SECURITY_BLOCK_SECONDS=900,
        ):
            for _ in range(3):
                bot._deliver_code(self.client_obj, "ajeno@gmail.com")
            msg = bot._deliver_code(
                self.client_obj, "mio@gmail.com", kind="signin_code"
            )
        self.assertIn("temporalmente bloqueado", msg)

    @mock.patch("codes.bot.threading.Timer")
    def test_sensitive_message_deletion_is_scheduled(self, mtimer):
        timer = mtimer.return_value
        with self.settings(CODES_SENSITIVE_MESSAGE_TTL_SECONDS=600):
            bot._schedule_sensitive_deletion(
                "888", send_result={"result": {"message_id": 321}}
            )
        mtimer.assert_called_once()
        self.assertEqual(mtimer.call_args.args[0], 600)
        self.assertTrue(timer.daemon)
        timer.start.assert_called_once()


class MenuButtonTests(TestCase):
    """Los botones del menú fijo equivalen a comandos."""

    def test_menu_buttons_map_to_known_commands(self):
        for label, cmd in bot.MENU_BUTTONS.items():
            self.assertTrue(
                cmd in bot.COMMAND_KINDS or cmd in ("/miscorreos", "/cmds"),
                f"{label} -> {cmd}",
            )

    @mock.patch("codes.bot.send_message")
    def test_tv_button_triggers_tv(self, msend):
        c = CodeBotClient.objects.create(telegram_chat_id="901", is_active=True)
        update = {
            "message": {
                "chat": {"id": 901},
                "from": {"username": "u", "first_name": "n"},
                "text": "📺 Activar TV",
            }
        }
        bot._handle_message(update)
        args, _ = msend.call_args
        self.assertIn(bot.NETFLIX_TV_ACTIVATION_URL, args[1])

    def test_persistent_keyboard_has_premium_icons_and_colors(self):
        keyboard = bot._menu_keyboard()["keyboard"]
        buttons = [button for row in keyboard for button in row]
        self.assertTrue(all(button.get("icon_custom_emoji_id") for button in buttons))
        self.assertEqual(
            {button.get("style") for button in buttons},
            {"primary", "success", "danger"},
        )
        self.assertEqual(
            [button["text"] for button in buttons],
            ["Código", "Viaje", "Hogar", "Clave", "Activar TV", "Mis correos"],
        )

    def test_inline_action_buttons_have_premium_icons_and_styles(self):
        buttons = bot._kind_buttons(0)
        action_buttons = [row[0] for row in buttons[:-1]]
        self.assertTrue(
            all(button.get("icon_custom_emoji_id") for button in action_buttons)
        )
        self.assertTrue(all(button.get("style") for button in action_buttons))

    def test_button_style_fallback_preserves_actions(self):
        markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "Código",
                        "callback_data": "c:signin_code:0",
                        "style": "primary",
                        "icon_custom_emoji_id": "123",
                    }
                ]
            ]
        }
        clean = bot._without_button_styling(markup)
        button = clean["inline_keyboard"][0][0]
        self.assertEqual(button["callback_data"], "c:signin_code:0")
        self.assertNotIn("style", button)
        self.assertNotIn("icon_custom_emoji_id", button)


class PremiumEmojiTests(TestCase):
    @override_settings(CODES_PREMIUM_EMOJI_KEY_ID="5368324170671202286")
    def test_configured_emoji_is_rendered_as_telegram_html(self):
        from codes.premium_emoji import render

        rendered = render("🔑 Tu código")
        self.assertIn(
            '<tg-emoji emoji-id="5368324170671202286">🔑</tg-emoji>',
            rendered,
        )

    @override_settings(CODES_PREMIUM_EMOJI_KEY_ID="")
    def test_empty_id_uses_jheliz_default(self):
        from codes.premium_emoji import render

        self.assertIn(
            '<tg-emoji emoji-id="5231250323779116601">🔑</tg-emoji>',
            render("🔑 Tu código"),
        )

    @override_settings(CODES_PREMIUM_EMOJI_WARNING_ID="")
    def test_unconfigured_emoji_without_default_keeps_unicode(self):
        from codes.premium_emoji import render

        self.assertEqual(render("⚠️ Atención"), "⚠️ Atención")

    @override_settings(CODES_PREMIUM_EMOJI_MAIL_ID="")
    def test_mis_correos_icon_uses_jheliz_default(self):
        from codes.premium_emoji import render

        self.assertIn(
            '<tg-emoji emoji-id="5008025248314950702">📋</tg-emoji>',
            render("📋 Mis correos"),
        )

    @override_settings(CODES_PREMIUM_EMOJI_CLIENTS_ID="")
    def test_admin_icon_uses_jheliz_default(self):
        from codes.premium_emoji import render

        self.assertIn(
            '<tg-emoji emoji-id="5343902827712367295">👥</tg-emoji>',
            render("👥 Clientes"),
        )

    @override_settings(
        CODES_PREMIUM_EMOJI_SEARCH_ID="",
        CODES_PREMIUM_EMOJI_TV_LINK_ID="",
    )
    def test_search_and_tv_link_use_jheliz_defaults(self):
        from codes.premium_emoji import render

        rendered = render("🔍 Buscar · 📨 Enlace TV")
        self.assertIn('emoji-id="5249245270381716113"', rendered)
        self.assertIn('emoji-id="5222102644734056755"', rendered)

    @override_settings(CODES_PREMIUM_EMOJI_KEY_ID="123")
    @mock.patch("codes.bot._call")
    def test_send_message_retries_with_unicode_if_custom_emoji_fails(self, mcall):
        mcall.side_effect = [
            {"ok": False, "description": "Bad Request"},
            {"ok": True, "result": {}},
        ]

        result = bot.send_message("42", "🔑 Tu código")

        self.assertTrue(result["ok"])
        self.assertEqual(mcall.call_count, 2)
        self.assertIn("<tg-emoji", mcall.call_args_list[0].kwargs["text"])
        self.assertEqual(mcall.call_args_list[1].kwargs["text"], "🔑 Tu código")

    def test_extracts_custom_emoji_id_from_replied_message(self):
        from codes.premium_emoji import custom_emoji_ids

        message = {
            "text": "/emojiid",
            "reply_to_message": {
                "text": "⭐",
                "entities": [
                    {
                        "type": "custom_emoji",
                        "offset": 0,
                        "length": 1,
                        "custom_emoji_id": "987654321",
                    }
                ],
            },
        }
        self.assertEqual(custom_emoji_ids(message), ["987654321"])
