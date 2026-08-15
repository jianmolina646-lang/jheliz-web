import re

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import User


class UserRoleTests(TestCase):
    def test_seller_can_manage_inventory(self) -> None:
        user = User(username="seller", role=User.Role.SELLER)
        self.assertTrue(user.can_manage_inventory)

    def test_viewer_cannot_manage_inventory(self) -> None:
        user = User(username="viewer", role=User.Role.VIEWER)
        self.assertFalse(user.can_manage_inventory)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordRecoveryTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="manager",
            email="manager@example.com",
            password="OldPassword-4821",
        )

    def test_sends_six_digit_code_and_changes_password(self) -> None:
        response = self.client.post(reverse("password_reset_request"), {"email": self.user.email})
        self.assertRedirects(response, reverse("password_reset_verify"))
        self.assertEqual(len(mail.outbox), 1)
        code = re.search(r"\b\d{6}\b", mail.outbox[0].body).group(0)
        response = self.client.post(
            reverse("password_reset_verify"),
            {"code": code, "password1": "NewPassword-5932", "password2": "NewPassword-5932"},
        )
        self.assertRedirects(response, reverse("password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPassword-5932"))
        self.assertNotIn("password_reset_challenge", self.client.session)

    def test_unknown_email_does_not_reveal_account(self) -> None:
        response = self.client.post(reverse("password_reset_request"), {"email": "unknown@example.com"})
        self.assertRedirects(response, reverse("password_reset_verify"))
        self.assertEqual(len(mail.outbox), 0)
        response = self.client.get(reverse("password_reset_verify"))
        self.assertContains(response, "Si el correo está registrado")
