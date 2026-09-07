"""Presentation checks using synthetic accounts and no Telegram requests."""

import html
from html.parser import HTMLParser
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from codes import bot
from codes.models import AssignedEmail, CodeBotClient
from codes.netflix import NetflixResult
from codes.premium_emoji import render, without_custom_emoji


class _Links(HTMLParser):
    def __init__(self, message):
        super().__init__()
        self.urls = []
        self.feed(message)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.urls.append(dict(attrs).get("href"))


class _TelegramMarkup(HTMLParser):
    """Check the subset of Telegram HTML used by the presentation templates."""

    def __init__(self, message):
        super().__init__()
        self.stack = []
        self.feed(message)
        assert not self.stack, f"Unclosed tags: {self.stack}"

    def handle_starttag(self, tag, attrs):
        assert tag in {"b", "i", "a", "code", "tg-emoji"}, tag
        assert "code" not in self.stack, "Code cannot contain other entities"
        if tag == "code":
            assert not self.stack, "Code cannot be nested inside formatting"
        self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack and self.stack.pop() == tag, f"Mismatched tag: {tag}"


class NetflixPresentationTests(SimpleTestCase):
    def test_templates_use_balanced_supported_telegram_entities(self):
        messages = [
            bot._client_help_text([]),
            bot._client_help_text(["synthetic@example.com"]),
            bot._client_help_text(["synthetic@example.com", "other@example.com"]),
            bot._admin_help_text(),
            bot._tv_activation_message(),
            bot._expired_message(),
            bot._account_actions_message("synthetic@example.com"),
            bot._searching_message("synthetic@example.com", "signin_code"),
            bot._format_result("synthetic@example.com", NetflixResult(kind="signin_code", code="123456")),
            bot._format_result("synthetic@example.com", NetflixResult(kind="password_reset", action_url="https://www.netflix.com/password?token=synthetic")),
        ]
        for message in messages:
            with self.subTest(message=message):
                _TelegramMarkup(message)
                _TelegramMarkup(render(message))

    def test_card_escapes_title_and_preserves_internal_body_html(self):
        title = 'Cuenta <VIP> & "Familia"'
        body = "<b>Cuenta activa</b>\n<code>123456</code>"

        message = bot._message_card(title, body, icon="📺")

        self.assertIn(html.escape(title), message)
        self.assertNotIn(title, message)
        self.assertIn(body, message)
        self.assertIn("NETFLIX", message)
        self.assertIn("TEAM JHELIZ", message)

    def test_search_masks_account_without_provider_or_promised_duration(self):
        email = "synthetic.customer@example.com"
        for kind in ("signin_code", "temp_code", "password_reset", "passwordless_signin"):
            with self.subTest(kind=kind):
                message = bot._searching_message(email, kind)

                self.assertIn("Buscando", message)
                self.assertIn(bot._mask_email(email), message)
                self.assertNotIn(email, message)
                self.assertNotIn("proton", message.lower())
                self.assertNotIn("imap", message.lower())
                self.assertNotRegex(message, r"\b\d+\s*(?:segundos?|minutos?|min|s)\b")

    def test_result_isolates_and_escapes_code(self):
        code = '12<34>&"56'
        email = "synthetic.customer@example.com"
        result = NetflixResult(kind="signin_code", code=code)

        message = bot._format_result(email, result)

        self.assertIn(f"<code>{html.escape(code)}</code>", message.splitlines())
        self.assertNotIn(code, message)
        self.assertIn(bot._mask_email(email), message)
        self.assertNotIn(email, message)
        self.assertIn("NETFLIX", message)
        self.assertIn("TEAM JHELIZ", message)
        self.assertNotRegex(message, r"\b15\s*min")

    def test_password_reset_url_survives_html_escaping(self):
        url = 'https://www.netflix.com/password?token=synthetic&label="Team <Jheliz>"'
        result = NetflixResult(kind="password_reset", action_url=url)

        message = bot._format_result("synthetic.customer@example.com", result)

        self.assertIn(f'href="{html.escape(url)}"', message)
        self.assertEqual(_Links(message).urls, [url])
        self.assertNotIn("<Jheliz>", message)

    def test_tv_page_and_email_signin_link_remain_distinct(self):
        url = "https://www.netflix.com/ilum?token=synthetic&source=email"
        email_result = NetflixResult(kind="passwordless_signin", action_url=url)

        tv_message = bot._tv_activation_message()
        email_message = bot._format_result("synthetic.customer@example.com", email_result)

        self.assertIn(bot.NETFLIX_TV_ACTIVATION_URL, _Links(tv_message).urls)
        self.assertEqual(_Links(email_message).urls, [url])
        self.assertNotIn(bot.NETFLIX_TV_ACTIVATION_URL, email_message)

    def test_tv_message_and_premium_render_are_valid_utf8(self):
        message = bot._tv_activation_message()
        rendered = render(message)

        self.assertTrue(message.encode("utf-8"))
        self.assertTrue(rendered.encode("utf-8"))
        self.assertEqual(without_custom_emoji(rendered), message)

    def test_keyboard_exposes_eight_actions_with_icons_and_known_styles(self):
        keyboard = bot._menu_keyboard()
        buttons = [button for row in keyboard["keyboard"] for button in row]

        self.assertEqual(
            [button["text"] for button in buttons],
            ["Código", "Enlace TV", "Viaje", "Hogar", "Clave", "Activar TV", "Mis correos", "Ayuda"],
        )
        self.assertTrue(all(button.get("icon_custom_emoji_id") for button in buttons))
        self.assertEqual({button.get("style") for button in buttons}, {"primary", "success", "danger"})
        self.assertTrue(keyboard["resize_keyboard"])
        self.assertTrue(keyboard["is_persistent"])

    def test_new_buttons_and_existing_aliases_keep_their_commands(self):
        aliases = {
            "enlace tv": "/enlacetv",
            "ayuda": "/cmds",
            "🔑 código": "/codigo",
            "✈️ viaje": "/viaje",
            "🏠 hogar": "/hogar",
            "🔒 clave": "/clave",
            "📺 activar tv": "/tv",
            "📋 mis correos": "/miscorreos",
            "❓ ayuda": "/cmds",
            "código": "/codigo",
            "viaje": "/viaje",
            "hogar": "/hogar",
            "clave": "/clave",
            "activar tv": "/tv",
            "mis correos": "/miscorreos",
        }
        for label, command in aliases.items():
            with self.subTest(label=label):
                self.assertEqual(bot.MENU_BUTTONS[label], command)

    def test_admin_help_includes_existing_operational_commands(self):
        message = bot._admin_help_text()

        for command in ("/clientes", "/asignar", "/anuncio", "/limite", "/diagnostico", "/metricas", "/emojiid"):
            with self.subTest(command=command):
                self.assertIn(command, message)


@override_settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900")
class NetflixPresentationFlowTests(TestCase):
    def setUp(self):
        self.client_obj = CodeBotClient.objects.create(
            telegram_chat_id="74001",
            display_name="Ana <b>VIP</b> & Sol",
            is_active=True,
        )
        AssignedEmail.objects.create(
            client=self.client_obj, email="synthetic.customer@example.com"
        )

    @mock.patch("codes.bot.send_message")
    def test_welcome_is_one_message_without_automatic_email_list(self, send):
        bot._send_welcome(self.client_obj)

        send.assert_called_once()
        message = send.call_args.args[1]
        self.assertTrue(send.call_args.kwargs.get("menu"))
        self.assertFalse(send.call_args.kwargs.get("buttons"))
        self.assertNotIn("synthetic.customer@example.com", message)
        self.assertNotIn(bot._mask_email("synthetic.customer@example.com"), message)
        self.assertNotIn(self.client_obj.display_name, message)
        self.assertNotIn("<b>VIP</b>", message)

    @mock.patch("codes.bot._cmd_tv_email")
    @mock.patch("codes.bot._cmd_tv")
    def test_enlace_tv_button_uses_existing_email_confirmation_flow(self, tv, email_tv):
        bot._handle_message(
            {"message": {"chat": {"id": 74001}, "text": "Enlace TV"}}
        )

        email_tv.assert_called_once_with(self.client_obj, "")
        tv.assert_not_called()

    @mock.patch("codes.bot._send_welcome")
    @mock.patch("codes.bot._send_commands_help")
    def test_ayuda_button_uses_existing_help_flow(self, help_message, welcome):
        bot._handle_message(
            {"message": {"chat": {"id": 74001}, "text": "Ayuda"}}
        )

        help_message.assert_called_once_with(self.client_obj)
        welcome.assert_not_called()
