from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings

from codes import bot
from codes.models import AssignedEmail, CodeBotClient, CodeDelivery
from codes.netflix import NetflixResult


@override_settings(
    CODES_COOLDOWN_SECONDS=0,
    CODES_RESULT_CACHE_SECONDS=5,
    CODES_DAILY_LIMIT=0,
    TELEGRAM_CODES_ADMIN_CHAT_ID="900",
)
class NetflixActionGuardTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.client_obj = CodeBotClient.objects.create(
            telegram_chat_id="73001", is_active=True
        )
        self.email = "assigned@example.com"
        AssignedEmail.objects.create(client=self.client_obj, email=self.email)
        self.enterContext(
            mock.patch("codes.bot.imap_reader.is_configured", return_value=True)
        )
        self.fetch = self.enterContext(
            mock.patch("codes.bot.imap_reader.fetch_latest_for_email", return_value=None)
        )
        self.send = self.enterContext(
            mock.patch("codes.bot.send_message", return_value={"ok": True})
        )
        self.edit = self.enterContext(mock.patch("codes.bot.edit_message"))
        self.answer = self.enterContext(mock.patch("codes.bot.answer_callback_query"))
        self.sleep = self.enterContext(mock.patch("codes.bot.time.sleep"))

    def _callback(self, data):
        bot._handle_callback(
            {
                "callback_query": {
                    "id": "guard-test",
                    "data": data,
                    "from": {"id": 73001},
                    "message": {"chat": {"id": 73001}, "message_id": 12},
                }
            }
        )

    def test_callbacks_reject_arbitrary_and_empty_types_before_delivery(self):
        with mock.patch("codes.bot._deliver_code") as deliver:
            for data in ("c:other:0", "c::0", "c:unknown:0", "c:email_change:0"):
                with self.subTest(data=data), mock.patch.object(cache, "get") as get:
                    self.answer.reset_mock()
                    self._callback(data)
                    self.answer.assert_called_once_with(
                        "guard-test", "Acción no permitida."
                    )
                    get.assert_not_called()
            deliver.assert_not_called()
        self.fetch.assert_not_called()
        self.send.assert_not_called()
        self.edit.assert_not_called()
        self.assertFalse(CodeDelivery.objects.exists())

    def test_non_string_callback_data_is_rejected(self):
        for data in (42, ["other"], {"kind": "other"}):
            with self.subTest(data=data):
                self.answer.reset_mock()
                self._callback(data)
                self.answer.assert_called_once_with(
                    "guard-test", "Acción no permitida."
                )
        self.fetch.assert_not_called()

    def test_delivery_rejects_invalid_types_before_reading_seeded_cache(self):
        cache.set(bot._result_cache_key(self.email, "other"), "unsafe-other-payload")
        cache.set(bot._result_cache_key(self.email, ""), "unsafe-any-payload")
        for kind in ("other", "", "unknown", 42, ["signin_code"], {"kind": "other"}):
            with (
                self.subTest(kind=kind),
                mock.patch.object(cache, "get") as get,
                mock.patch.object(cache, "set") as set_cache,
            ):
                message = bot._deliver_code(self.client_obj, self.email, kind=kind)
                self.assertIn("Acción no permitida", message)
                self.assertNotIn("unsafe", message)
                get.assert_not_called()
                set_cache.assert_not_called()
        self.fetch.assert_not_called()
        self.assertFalse(CodeDelivery.objects.exists())

    def test_unexpected_results_are_never_formatted_logged_as_success_or_cached(self):
        for requested, returned in (
            ("signin_code", "other"),
            ("signin_code", "password_reset"),
            ("password_reset", "signin_code"),
            ("passwordless_signin", "password_reset"),
            ("tv_signin", "passwordless_signin"),
            (None, "other"),
            (None, "unknown"),
            (None, ""),
            (None, ["signin_code"]),
        ):
            with self.subTest(requested=requested, returned=returned):
                self.fetch.return_value = NetflixResult(
                    kind=returned,
                    code="987654",
                    action_url="https://www.netflix.com/account/unsafe-payload",
                )
                with mock.patch("codes.bot._format_result") as formatter:
                    message = bot._deliver_code(
                        self.client_obj, self.email, kind=requested
                    )
                    formatter.assert_not_called()
                self.assertIn("No encontré", message)
                self.assertNotIn("987654", message)
                self.assertNotIn("unsafe-payload", message)
                self.assertIsNone(cache.get(bot._result_cache_key(self.email, requested)))
        self.assertFalse(CodeDelivery.objects.filter(found=True).exists())
        self.assertFalse(
            CodeDelivery.objects.exclude(payload_fingerprint="").exists()
        )

    def test_polling_can_recover_after_an_unexpected_result(self):
        self.fetch.side_effect = [
            NetflixResult(kind="other", code="987654"),
            NetflixResult(kind="signin_code", code="246810"),
        ]
        message = bot._deliver_code(
            self.client_obj, self.email, kind="signin_code", wait_seconds=2
        )
        self.assertIn("246810", message)
        self.assertNotIn("987654", message)
        self.assertEqual(self.fetch.call_count, 2)
        self.sleep.assert_called_once_with(2)
        self.assertTrue(CodeDelivery.objects.get().found)

    def test_legacy_malformed_and_wrong_kind_cache_entries_are_ignored(self):
        key = bot._result_cache_key(self.email, "signin_code")
        for entry in (
            "unsafe-legacy-payload",
            ["unsafe-malformed-payload"],
            {"message": "unsafe-untyped-payload"},
            {"kind": "other", "message": "unsafe-other-payload"},
            {"kind": "password_reset", "message": "unsafe-wrong-kind-payload"},
            {"kind": ["signin_code"], "message": "unsafe-malformed-kind"},
            {"kind": "signin_code", "message": ["unsafe-malformed-message"]},
        ):
            with self.subTest(entry=entry):
                cache.set(key, entry)
                self.fetch.reset_mock()
                message = bot._deliver_code(
                    self.client_obj, self.email, kind="signin_code"
                )
                self.assertIn("No encontré", message)
                self.assertNotIn("unsafe", message)
                self.fetch.assert_called_once_with(self.email, kind="signin_code")
        self.assertFalse(CodeDelivery.objects.filter(found=True).exists())

    def test_allowed_result_is_cached_with_kind_and_reused(self):
        self.fetch.return_value = NetflixResult(kind="signin_code", code="246810")
        first = bot._deliver_code(self.client_obj, self.email, kind="signin_code")
        second = bot._deliver_code(self.client_obj, self.email, kind="signin_code")
        self.assertIn("246810", first)
        self.assertEqual(first, second)
        self.fetch.assert_called_once_with(self.email, kind="signin_code")
        self.assertEqual(
            cache.get(bot._result_cache_key(self.email, "signin_code")),
            {"kind": "signin_code", "message": first},
        )
        self.assertEqual(CodeDelivery.objects.filter(found=True).count(), 1)

    def test_internal_unspecified_kind_keeps_known_results_available(self):
        self.fetch.return_value = NetflixResult(kind="temp_code", code="246810")
        message = bot._deliver_code(self.client_obj, self.email)
        self.assertIn("246810", message)
        self.fetch.assert_called_once_with(self.email, kind=None)
        self.assertTrue(CodeDelivery.objects.get().found)

    def test_clave_command_delivers_to_active_assigned_client(self):
        url = "https://www.netflix.com/password?token=legitimate-reset"
        self.fetch.return_value = NetflixResult(kind="password_reset", action_url=url)
        bot._handle_message(
            {
                "message": {
                    "chat": {"id": 73001},
                    "from": {"id": 73001},
                    "text": f"/clave {self.email}",
                }
            }
        )
        self.fetch.assert_called_once_with(self.email, kind="password_reset")
        self.assertIn(url, self.send.call_args.args[1])
        delivery = CodeDelivery.objects.get()
        self.assertTrue(delivery.found)
        self.assertEqual(delivery.kind, "password_reset")

    def test_password_reset_callback_remains_available(self):
        url = "https://www.netflix.com/password?token=legitimate-reset"
        self.fetch.return_value = NetflixResult(kind="password_reset", action_url=url)
        self._callback("c:password_reset:0")
        self.fetch.assert_called_once_with(self.email, kind="password_reset")
        self.assertIn(url, self.edit.call_args.args[2])
        self.assertTrue(CodeDelivery.objects.get().found)

    def test_tv_email_confirmation_accepts_both_supported_result_types(self):
        for kind in ("passwordless_signin", "tv_signin"):
            with self.subTest(kind=kind):
                cache.clear()
                self.fetch.reset_mock()
                url = f"https://www.netflix.com/accountaccess?token={kind}"
                self.fetch.return_value = NetflixResult(kind=kind, action_url=url)
                self._callback("tvconfirm:0")
                self.fetch.assert_called_once_with(
                    self.email, kind=("passwordless_signin", "tv_signin")
                )
                self.assertIn(url, self.edit.call_args.args[2])
        self.assertEqual(CodeDelivery.objects.filter(found=True).count(), 2)

    def test_tv_action_keeps_activation_page_without_imap(self):
        self._callback("c:tv_signin:0")
        self.assertIn(bot.NETFLIX_TV_ACTIVATION_URL, self.edit.call_args.args[2])
        bot._handle_message(
            {"message": {"chat": {"id": 73001}, "text": "/tv"}}
        )
        self.assertIn(bot.NETFLIX_TV_ACTIVATION_URL, self.send.call_args.args[1])
        self.fetch.assert_not_called()
        self.assertFalse(CodeDelivery.objects.exists())
