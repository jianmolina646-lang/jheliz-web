from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from gestion.models import TelegramConnection, Tenant
from gestion.admin import TenantAdmin
from gestion.tenant_views import password_recovery_token_generator


@override_settings(
    SECURE_SSL_REDIRECT=False,
    ROOT_URLCONF="gestion.tenant_urls",
)
class TenantPasswordRecoveryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="recovery-user", password="old-safe-password-123"
        )
        Tenant.objects.create(user=self.user)

    @patch("gestion.telegram_alerts.send_message")
    def test_unlinked_account_gets_generic_response_without_delivery(self, send):
        response = self.client.post(
            reverse("jheliztv_password_recovery"), {"username": self.user.username}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Si el usuario existe")
        send.assert_not_called()

    @patch("gestion.telegram_alerts.send_message")
    def test_linked_account_receives_one_use_link_and_changes_only_password(self, send):
        TelegramConnection.objects.create(
            owner=self.user, chat_id="123456", is_enabled=True
        )
        response = self.client.post(
            reverse("jheliztv_password_recovery"), {"username": self.user.username}
        )
        self.assertEqual(response.status_code, 200)
        send.assert_called_once()
        message = send.call_args.args[1]
        link = message.split('href="', 1)[1].split('"', 1)[0]
        confirm_path = urlsplit(link).path
        response = self.client.get(confirm_path)
        self.assertEqual(response.status_code, 302)
        set_password_path = response["Location"]
        response = self.client.post(
            set_password_path,
            {
                "new_password1": "new-safe-password-456",
                "new_password2": "new-safe-password-456",
            },
        )
        self.assertRedirects(
            response, reverse("jheliztv_password_recovery_complete")
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new-safe-password-456"))
        self.assertEqual(Tenant.objects.filter(user=self.user).count(), 1)

    @patch("gestion.telegram_alerts.send_message")
    def test_unknown_username_does_not_reveal_account_existence(self, send):
        response = self.client.post(
            reverse("jheliztv_password_recovery"), {"username": "does-not-exist"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Si el usuario existe")
        send.assert_not_called()

    def test_token_expires_after_fifteen_minutes(self):
        token = password_recovery_token_generator.make_token(self.user)
        future = password_recovery_token_generator._now() + timedelta(minutes=16)
        with patch.object(password_recovery_token_generator, "_now", return_value=future):
            self.assertFalse(
                password_recovery_token_generator.check_token(self.user, token)
            )

    def test_admin_action_generates_link_without_changing_password(self):
        admin_model = TenantAdmin(Tenant, AdminSite())
        request = RequestFactory().post("/admin/")
        request.user = get_user_model().objects.create_superuser(
            username="recovery-admin", password="admin-safe-password-123"
        )
        tenant = Tenant.objects.get(user=self.user)
        with patch.object(admin_model, "message_user") as message_user:
            admin_model.generate_password_recovery_link(
                request, Tenant.objects.filter(pk=tenant.pk)
            )
        rendered_message = str(message_user.call_args.args[1])
        self.assertIn("/recuperar/", rendered_message)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("old-safe-password-123"))

    def test_owner_panel_generates_link_without_changing_password(self):
        owner = get_user_model().objects.create_superuser(
            username="control-owner", password="owner-safe-password-123"
        )
        self.client.force_login(owner)
        with self.settings(ROOT_URLCONF="config.urls_jheliztv"):
            response = self.client.post(
                reverse("jheliztv_control_password_recovery"),
                {"username": self.user.username},
                HTTP_HOST="jheliztv.xyz",
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/recuperar/", response.content)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("old-safe-password-123"))
