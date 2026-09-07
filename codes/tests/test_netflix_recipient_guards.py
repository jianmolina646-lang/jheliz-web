"""Regresiones de aislamiento del destinatario usando solo correos ficticios."""

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from unittest import mock

from django.test import SimpleTestCase, override_settings

from codes import imap_reader
from codes.disney import parse_disney_email
from codes.netflix import parse_netflix_email


class NetflixRecipientGuardTests(SimpleTestCase):
    requested = "ana@example.com"

    def message(self, recipient="ana@example.com", body=None, **headers):
        msg = EmailMessage()
        msg["From"] = "Netflix <info@account.netflix.com>"
        msg["To"] = recipient
        msg["Subject"] = "Your Netflix sign-in code"
        msg["Date"] = format_datetime(datetime.now(timezone.utc))
        for name, value in headers.items():
            msg[name] = value
        msg.set_content(body or "Netflix sign-in code: 123456")
        return msg

    def search(self, messages, kind="signin_code", service="netflix"):
        conn = mock.Mock()
        conn.search.return_value = (
            "OK", [b" ".join(str(i).encode() for i in range(1, len(messages) + 1))]
        )
        conn.fetch.side_effect = lambda ident, _: (
            "OK", [(b"1 (BODY[]", messages[int(ident) - 1].as_bytes())]
        )
        parser = parse_netflix_email if service == "netflix" else parse_disney_email
        with mock.patch.object(imap_reader, "_connect", return_value=conn):
            results = imap_reader._search_account(
                {"user": "synthetic", "password": "synthetic"},
                self.requested, service, parser, kind,
                datetime.now(timezone.utc) - timedelta(minutes=15),
                service=service,
            )
        conn.select.assert_called_once_with("INBOX", readonly=True)
        self.assertTrue(all(call.args[1] == "(BODY.PEEK[] INTERNALDATE)" for call in conn.fetch.call_args_list))
        return results

    def test_exact_recipient_still_delivers_code(self):
        results = self.search([self.message()])
        self.assertEqual(results[0][1].code, "123456")

    def test_recipient_case_and_display_name_are_supported(self):
        results = self.search([self.message("Ana <ANA@EXAMPLE.COM>")])
        self.assertEqual(results[0][1].code, "123456")

    def test_other_recipient_with_same_suffix_is_rejected(self):
        self.assertEqual(self.search([self.message("mariana@example.com")]), [])

    def test_similar_domains_plus_tags_and_display_name_do_not_authorize(self):
        for address in (
            "ana@example.com.evil.test",
            "ana+extra@example.com",
            '"ana@example.com" <other@example.net>',
        ):
            with self.subTest(address=address):
                self.assertEqual(self.search([self.message(address)]), [])

    def test_plain_body_mention_does_not_authorize(self):
        msg = self.message("other@example.com", "Netflix sign-in code: 123456. Contact: ana@example.com")
        self.assertEqual(self.search([msg]), [])

    def test_subject_and_from_mentions_do_not_authorize(self):
        msg = self.message("other@example.com")
        msg.replace_header("From", '"ana@example.com" <info@account.netflix.com>')
        msg.replace_header("Subject", "Netflix sign-in code for ana@example.com")
        self.assertEqual(self.search([msg]), [])

    def test_quoted_forwarded_body_header_does_not_authorize(self):
        msg = self.message("relay@example.net", "Forwarded message\nTo: ana@example.com\nNetflix sign-in code: 123456")
        self.assertEqual(self.search([msg]), [])

    def test_html_mention_does_not_authorize(self):
        msg = self.message("relay@example.net")
        msg.add_alternative('<p>Netflix sign-in code: 123456</p><a href="mailto:ana@example.com">Contact</a>', subtype="html")
        self.assertEqual(self.search([msg]), [])

    def test_exact_original_recipient_headers_preserve_automatic_forwarding(self):
        for header in imap_reader._RECIPIENT_HEADERS:
            if header == "To":
                continue
            with self.subTest(header=header):
                msg = self.message("relay@example.net", **{header: self.requested})
                self.assertEqual(self.search([msg])[0][1].code, "123456")

    def test_similar_original_recipient_is_rejected(self):
        for header in imap_reader._RECIPIENT_HEADERS:
            if header == "To":
                continue
            with self.subTest(header=header):
                msg = self.message("relay@example.net", **{header: "mariana@example.com"})
                self.assertEqual(self.search([msg]), [])

    def test_scan_skips_wrong_newer_recipient_and_finds_exact_account(self):
        exact = self.message(body="Netflix sign-in code: 654321")
        wrong_newer = self.message("mariana@example.com")
        results = self.search([exact, wrong_newer])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][1].code, "654321")

    def test_password_reset_for_exact_account_remains_allowed(self):
        msg = self.message(body="Reset your password: https://www.netflix.com/password?token=synthetic")
        msg.replace_header("Subject", "Reset your Netflix password")
        results = self.search([msg], kind="password_reset")
        self.assertEqual(results[0][1].kind, "password_reset")
        self.assertIn("/password?", results[0][1].action_url)

    def test_explicit_other_kind_never_returns_unrecognized_netflix_mail(self):
        msg = self.message(body="Netflix: https://www.netflix.com/email?token=synthetic")
        msg.replace_header("Subject", "Account notification")
        self.assertEqual(self.search([msg], kind="other"), [])

    def test_disney_legacy_recipient_matching_is_unchanged(self):
        msg = self.message("relay@example.net", "Disney+ sign-in code: 123456. Contact: ana@example.com")
        msg.replace_header("Subject", "Your one-time passcode for Disney+")
        results = self.search([msg], service="disney")
        self.assertEqual(results[0][1].code, "123456")

    @override_settings(CODES_IMAP_HOST="imap.example.net", CODES_IMAP_USER="synthetic", CODES_IMAP_PASSWORD="synthetic", CODES_IMAP2_HOST="")
    def test_reader_passes_service_to_recipient_policy(self):
        for service in ("netflix", "disney"):
            with self.subTest(service=service), mock.patch.object(imap_reader, "_search_account", return_value=[]) as search:
                self.assertIsNone(imap_reader.fetch_latest_for_email(self.requested, service=service))
                self.assertEqual(search.call_args.kwargs["service"], service)
