from django.test import TestCase

from gestion.models import TelegramSentMessage
from gestion.telegram_messages import record_sent_message


class TelegramMessageRegistryTests(TestCase):
    def test_records_only_identifiers(self):
        record_sent_message(
            "store",
            {"chat_id": "123", "text": "no debe persistirse"},
            {"ok": True, "result": {"message_id": 77, "chat": {"id": 123}}},
        )
        saved = TelegramSentMessage.objects.get()
        self.assertEqual(saved.bot_key, "store")
        self.assertEqual(saved.chat_id, "123")
        self.assertEqual(saved.message_id, 77)

    def test_ignores_failed_responses(self):
        record_sent_message("store", {"chat_id": "123"}, {"ok": False})
        self.assertFalse(TelegramSentMessage.objects.exists())
