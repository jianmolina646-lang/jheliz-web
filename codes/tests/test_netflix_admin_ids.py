"""Operaciones por ID con nombres que no son HTML válido de Telegram."""

from unittest import mock

from django.test import TestCase, override_settings

from codes import bot
from codes.models import AssignedEmail, CodeBotClient
from codes.tests.test_netflix_presentation import _TelegramMarkup


@override_settings(TELEGRAM_CODES_ADMIN_CHAT_ID="900")
class NetflixAdminIdTests(TestCase):
    @mock.patch("codes.bot.send_message", return_value={"ok": True})
    def test_id_operations_and_repeated_requests_with_identical_unsafe_names(self, send):
        target = CodeBotClient.objects.create(
            telegram_chat_id="424242", display_name="Ana <VIP> & equipo",
        )
        other = CodeBotClient.objects.create(
            telegram_chat_id="424243", display_name=target.display_name,
        )
        AssignedEmail.objects.create(client=target, email="keep@example.com")
        AssignedEmail.objects.create(client=other, email="shared@example.com")
        operations = (
            ("/activar 424242", True, ["keep@example.com"]),
            ("/desactivar 424242", False, ["keep@example.com"]),
            ("/asignar 424242 shared@example.com", True, ["keep@example.com", "shared@example.com"]),
            ("/quitar 424242 shared@example.com", True, ["keep@example.com"]),
        )
        for command, active, emails in operations:
            for attempt in range(2):
                with self.subTest(command=command, attempt=attempt):
                    send.reset_mock()
                    bot.process_update({"message": {
                        "chat": {"id": 900, "type": "private"},
                        "from": {"id": 900, "first_name": "Administrador"},
                        "text": command,
                    }})
                    target.refresh_from_db()
                    other.refresh_from_db()
                    self.assertEqual(target.is_active, active)
                    self.assertEqual(list(target.emails.values_list("email", flat=True)), emails)
                    self.assertFalse(other.is_active)
                    self.assertEqual(list(other.emails.values_list("email", flat=True)), ["shared@example.com"])
                    admin_replies = [call.args[1] for call in send.call_args_list if str(call.args[0]) == "900"]
                    self.assertEqual(len(admin_replies), 1)
                    self.assertIn("<code>424242</code>", admin_replies[0])
                    for call in send.call_args_list:
                        _TelegramMarkup(call.args[1])
