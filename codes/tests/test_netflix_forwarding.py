"""Reenvíos Outlook autenticados: fixtures ficticios, sin correos reales."""

from email.message import EmailMessage
from unittest import TestCase

from codes.forwarding import matches_outlook_forward


class NetflixForwardingTests(TestCase):
    target = "ana@outlook.com"
    authserv = "mail.protonmail.ch"
    dmarc = "dmarc=pass header.from=outlook.com"
    dkim = "dkim=pass header.d=outlook.com"

    def message(self, *, html=False, target=None):
        recipient = target or self.target
        msg = EmailMessage()
        msg["From"] = f"Ana <{self.target}>"
        msg["To"] = "relay@example.net"
        msg["Subject"] = "RV: Tu código de acceso temporal"
        msg["Auto-Submitted"] = "auto-generated"
        msg["X-Ms-Exchange-Inbox-Rules-Loop"] = self.target
        msg["Authentication-Results"] = f"{self.authserv}; {self.dmarc}"
        msg["Authentication-Results"] = f"{self.authserv}; {self.dkim}"
        content = (
            "De: Netflix <info@account.netflix.com>\n"
            "Enviados: martes, 8 de septiembre de 2026 9:00\n"
            f"Para: Ana <{recipient}>\n"
            "Asunto: Tu código de acceso temporal\n\n"
            "Netflix: obtener código de acceso temporal.\n"
            "https://www.netflix.com/account/travel/verify?token=synthetic"
        )
        if html:
            content = (
                '<html><head><style>.test { color: red; }</style></head><body>'
                '<div><br></div><hr><div id="divRplyFwdMsg">'
                '<b>De:</b>&nbsp;Netflix &lt;info@account.netflix.com&gt;<br>'
                '<b>Enviados:</b>&nbsp;martes, 8 de septiembre de 2026 9:00<br>'
                f'<b>Para:</b>&nbsp;Ana &lt;{recipient}&gt;<br>'
                '<b>Asunto:</b>&nbsp;Tu código de acceso temporal</div>'
                '<p>Netflix: obtener código de acceso temporal.</p>'
                '<a href="https://www.netflix.com/account/travel/verify?token=synthetic">'
                'Obtener código</a></body></html>'
            )
        msg.set_content(content, subtype="html" if html else "plain")
        return msg

    def matches(self, msg, trusted=None):
        return matches_outlook_forward(
            msg, self.target,
            trusted_authserv_id=self.authserv if trusted is None else trusted,
        )

    def auth(self, msg, *headers):
        del msg["Authentication-Results"]
        for header in headers:
            msg["Authentication-Results"] = header

    def test_plain_and_html_outlook_rules_match(self):
        for html in (False, True):
            with self.subTest(html=html):
                self.assertTrue(self.matches(self.message(html=html)))

    def test_comparison_is_case_insensitive(self):
        msg = self.message(target=self.target.upper())
        msg.replace_header("From", self.target.upper())
        msg.replace_header("X-Ms-Exchange-Inbox-Rules-Loop", self.target.upper())
        self.assertTrue(self.matches(msg))

    def test_trust_must_be_explicit_and_exact(self):
        for trusted in ("", "protonmail.ch", "mail.protonmail.ch.evil.test"):
            with self.subTest(trusted=trusted):
                self.assertFalse(self.matches(self.message(), trusted=trusted))

    def test_from_must_be_one_exact_address(self):
        for sender in (
            "mariana@outlook.com", "ana+tag@outlook.com",
            "ana@outlook.com.evil.test", '"ana@outlook.com" <other@outlook.com>',
            "ana@outlook.com, other@outlook.com",
        ):
            with self.subTest(sender=sender):
                msg = self.message()
                msg.replace_header("From", sender)
                self.assertFalse(self.matches(msg))

    def test_duplicate_from_is_rejected(self):
        msg = self.message()
        msg._headers.append(("From", self.target))
        self.assertFalse(self.matches(msg))

    def test_other_provider_is_not_enabled(self):
        msg = self.message(target="ana@hotmail.com")
        msg.replace_header("From", "ana@hotmail.com")
        msg.replace_header("X-Ms-Exchange-Inbox-Rules-Loop", "ana@hotmail.com")
        self.assertFalse(matches_outlook_forward(
            msg, "ana@hotmail.com", trusted_authserv_id=self.authserv,
        ))

    def test_rule_markers_are_required_and_exact(self):
        for header, replacement in (
            ("Auto-Submitted", None), ("Auto-Submitted", "no"),
            ("Auto-Submitted", "auto-replied"),
            ("X-Ms-Exchange-Inbox-Rules-Loop", None),
            ("X-Ms-Exchange-Inbox-Rules-Loop", "mariana@outlook.com"),
        ):
            with self.subTest(header=header, replacement=replacement):
                msg = self.message()
                del msg[header]
                if replacement is not None:
                    msg[header] = replacement
                self.assertFalse(self.matches(msg))

    def test_duplicate_rule_markers_are_rejected(self):
        for header in ("Auto-Submitted", "X-Ms-Exchange-Inbox-Rules-Loop"):
            with self.subTest(header=header):
                msg = self.message()
                msg[header] = str(msg[header])
                self.assertFalse(self.matches(msg))

    def test_original_to_must_be_one_exact_address(self):
        for recipient in (
            "mariana@outlook.com", "ana+tag@outlook.com", "ana@outlook.com.evil.test",
        ):
            for html in (False, True):
                with self.subTest(recipient=recipient, html=html):
                    self.assertFalse(self.matches(self.message(html=html, target=recipient)))
        msg = self.message()
        msg.set_content(msg.get_content().replace(
            f"Para: Ana <{self.target}>",
            f'Para: "{self.target}" <other@outlook.com>',
        ))
        self.assertFalse(self.matches(msg))

    def test_outlook_original_to_can_repeat_the_exact_address_as_display_name(self):
        for html in (False, True):
            with self.subTest(html=html):
                msg = self.message(html=html)
                msg.set_content(
                    msg.get_content().replace("Ana ", f"{self.target} "),
                    subtype="html" if html else "plain",
                )
                self.assertTrue(self.matches(msg))

    def test_outlook_repeated_address_requires_both_addresses_to_match(self):
        for display, address in (
            (self.target, "other@outlook.com"),
            ("other@outlook.com", self.target),
        ):
            for html in (False, True):
                with self.subTest(display=display, address=address, html=html):
                    msg = self.message(html=html, target=address)
                    msg.set_content(
                        msg.get_content().replace("Ana ", f"{display} "),
                        subtype="html" if html else "plain",
                    )
                    self.assertFalse(self.matches(msg))
        msg = self.message()
        msg.set_content(msg.get_content().replace(
            f"Para: Ana <{self.target}>",
            f"Para: {self.target}, other@outlook.com",
        ))
        self.assertFalse(self.matches(msg))

    def test_original_sender_domain_is_exact(self):
        for sender in ("info@account.netflix.com.evil.test", "info@evilnetflix.com"):
            with self.subTest(sender=sender):
                msg = self.message()
                msg.set_content(msg.get_content().replace("info@account.netflix.com", sender))
                self.assertFalse(self.matches(msg))

    def test_body_mentions_and_later_forwarded_blocks_do_not_authorize(self):
        for prefix in ("Contact: ana@outlook.com\n", "Forwarded message\n", "Texto ajeno\n"):
            with self.subTest(prefix=prefix):
                msg = self.message()
                msg.set_content(prefix + msg.get_content())
                self.assertFalse(self.matches(msg))
        msg = self.message(target="other@outlook.com")
        msg.set_content(msg.get_content() + "\n" + self.message().get_content())
        self.assertFalse(self.matches(msg))

    def test_incomplete_or_reordered_original_headers_are_rejected(self):
        for original, replacement in (
            ("Enviados:", "Contact:"), ("Para:", "Cc:"), ("Asunto:", "Texto:"),
        ):
            with self.subTest(original=original):
                msg = self.message()
                msg.set_content(msg.get_content().replace(original, replacement))
                self.assertFalse(self.matches(msg))

    def test_dmarc_and_dkim_are_both_required(self):
        for result in (self.dmarc, self.dkim, "spf=pass smtp.mailfrom=outlook.com"):
            with self.subTest(result=result):
                msg = self.message()
                self.auth(msg, f"{self.authserv}; {result}")
                self.assertFalse(self.matches(msg))

    def test_failed_missing_or_unaligned_results_are_rejected(self):
        for result in (
            "dmarc=fail header.from=outlook.com", "dmarc=none header.from=outlook.com",
            "dmarc=pass", "dmarc=pass header.from=outlook.com.evil.test",
            "dkim=fail header.d=outlook.com", "dkim=pass header.d=hotmail.com",
            "dkim=pass header.i=@outlook.com",
        ):
            with self.subTest(result=result):
                msg = self.message()
                self.auth(msg, f"{self.authserv}; {result}; {self.dmarc}; {self.dkim}")
                self.assertFalse(self.matches(msg))

    def test_later_pass_cannot_override_failure_or_conflicting_domain(self):
        for method, prop in (("dmarc", "header.from"), ("dkim", "header.d")):
            for result in (f"{method}=fail {prop}=outlook.com", f"{method}=pass {prop}=evil.test"):
                for first in (True, False):
                    with self.subTest(result=result, first=first):
                        msg = self.message()
                        headers = [f"{self.authserv}; {self.dmarc}; {self.dkim}"]
                        headers.insert(0 if first else 1, f"{self.authserv}; {result}")
                        self.auth(msg, *headers)
                        self.assertFalse(self.matches(msg))

    def test_unknown_authserv_and_arc_do_not_authorize(self):
        for authserv in ("evil.test", f"{self.authserv}.evil.test", f"evil.{self.authserv}"):
            with self.subTest(authserv=authserv):
                msg = self.message()
                self.auth(msg, f"{authserv}; {self.dmarc}; {self.dkim}")
                self.assertFalse(self.matches(msg))
        msg = self.message()
        self.auth(msg)
        msg["ARC-Authentication-Results"] = f"i=1; {self.authserv}; {self.dmarc}; {self.dkim}"
        self.assertFalse(self.matches(msg))

    def test_comments_and_quoted_reasons_are_not_authentication_methods(self):
        for field in (
            f"spf=pass ({self.dmarc}; {self.dkim}) smtp.mailfrom=outlook.com",
            f'spf=pass reason="{self.dmarc}; {self.dkim}" smtp.mailfrom=outlook.com',
            f"({self.dmarc}; {self.dkim}) spf=pass smtp.mailfrom=outlook.com",
        ):
            with self.subTest(field=field):
                msg = self.message()
                self.auth(msg, f"{self.authserv}; {field}")
                self.assertFalse(self.matches(msg))

    def test_real_comments_quoted_domains_and_extra_methods_are_supported(self):
        msg = self.message()
        self.auth(msg,
            f'{self.authserv}; spf=pass smtp.mailfrom=outlook.com; '
            'dmarc=pass (p=none dis=none) header.from="outlook.com"',
            f'{self.authserv}; dkim=pass (2048-bit key) header.d="outlook.com" '
            'header.i=@outlook.com header.b=synthetic',
        )
        self.assertTrue(self.matches(msg))

    def test_malformed_and_ambiguous_authentication_results_fail_closed(self):
        for field in (
            "dmarc=pass (unterminated", 'dmarc=pass header.from="outlook.com',
            "dmarc=pass header.from=outlook.com header.from=evil.test",
            "dmarc=passheader.from=outlook.com", "dmarc=pass) header.from=outlook.com",
        ):
            with self.subTest(field=field):
                msg = self.message()
                self.auth(msg, f"{self.authserv}; {field}; {self.dmarc}; {self.dkim}")
                self.assertFalse(self.matches(msg))

    def test_conflicting_mime_representations_are_rejected(self):
        msg = self.message()
        msg.add_alternative(self.message(html=True, target="other@outlook.com").get_content(), subtype="html")
        self.assertFalse(self.matches(msg))

    def test_matching_mime_representations_are_supported(self):
        msg = self.message()
        msg.add_alternative(self.message(html=True).get_content(), subtype="html")
        self.assertTrue(self.matches(msg))

    def test_empty_visible_html_cannot_hide_another_action(self):
        msg = self.message()
        msg.add_alternative(
            '<a href="https://www.netflix.com/password?token=synthetic"></a>',
            subtype="html",
        )
        self.assertFalse(self.matches(msg))

    def test_attached_message_cannot_supply_authentication_or_original_headers(self):
        msg = self.message()
        self.auth(msg)
        msg.add_attachment(self.message())
        self.assertFalse(self.matches(msg))
        msg = self.message()
        msg.add_attachment(self.message(html=True, target="other@outlook.com"))
        self.assertFalse(self.matches(msg))
        msg = self.message()
        msg.set_content("Sin bloque de destinatario original")
        msg.add_attachment(self.message())
        self.assertFalse(self.matches(msg))

    def test_body_without_original_block_is_rejected(self):
        msg = self.message()
        msg.set_content("Netflix sign-in code: 123456. Contact: ana@outlook.com")
        self.assertFalse(self.matches(msg))
