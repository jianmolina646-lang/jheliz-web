from cryptography.fernet import Fernet
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from inventory.models import DigitalAccount
from services.models import DigitalService

from .forms import ReplacementForm
from .models import Replacement


@override_settings(ACCOUNT_CREDENTIAL_KEY=Fernet.generate_key().decode("ascii"))
class ReplacementTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="manager", password="Test-Password-987", role=User.Role.ADMIN
        )
        self.viewer = User.objects.create_user(
            username="viewer", password="Test-Password-987", role=User.Role.VIEWER
        )
        self.service = DigitalService.objects.create(name="Netflix")
        self.original = self.create_account("anterior@example.com", DigitalAccount.Status.SOLD)
        self.replacement_account = self.create_account(
            "nueva@example.com", DigitalAccount.Status.AVAILABLE
        )

    def create_account(self, email, status, service=None):
        return DigitalAccount.objects.create(
            service=service or self.service,
            email=email,
            status=status,
            created_by=self.manager,
        )

    def replacement_data(self, original=None, replacement=None):
        return {
            "original_account": (original or self.original).pk,
            "replacement_account": (replacement or self.replacement_account).pk,
            "reason": Replacement.Reason.ACCESS,
            "replaced_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "notes": "Reposición verificada",
        }

    def test_manager_replaces_account_atomically(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("replacements:create"), self.replacement_data())
        replacement = Replacement.objects.get(original_account=self.original)
        self.assertRedirects(response, reverse("replacements:detail", args=[replacement.pk]))
        self.original.refresh_from_db()
        self.replacement_account.refresh_from_db()
        self.assertEqual(self.original.status, DigitalAccount.Status.RETIRED)
        self.assertEqual(self.replacement_account.status, DigitalAccount.Status.SOLD)

    def test_accounts_from_different_services_are_rejected_without_changes(self):
        other_service = DigitalService.objects.create(name="Prime Video")
        wrong_account = self.create_account(
            "prime@example.com", DigitalAccount.Status.AVAILABLE, service=other_service
        )
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("replacements:create"),
            self.replacement_data(replacement=wrong_account),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Replacement.objects.exists())
        self.original.refresh_from_db()
        wrong_account.refresh_from_db()
        self.assertEqual(self.original.status, DigitalAccount.Status.SOLD)
        self.assertEqual(wrong_account.status, DigitalAccount.Status.AVAILABLE)

    def test_replaced_original_is_not_offered_again(self):
        Replacement.objects.create(
            original_account=self.original,
            replacement_account=self.replacement_account,
            reason=Replacement.Reason.BLOCKED,
            created_by=self.manager,
        )
        form = ReplacementForm()
        self.assertNotIn(self.original, form.fields["original_account"].queryset)

    def test_replacement_can_later_become_origin_of_a_traced_chain(self):
        Replacement.objects.create(
            original_account=self.original,
            replacement_account=self.replacement_account,
            reason=Replacement.Reason.BLOCKED,
            created_by=self.manager,
        )
        self.original.status = DigitalAccount.Status.RETIRED
        self.original.save(update_fields=("status",))
        self.replacement_account.status = DigitalAccount.Status.SOLD
        self.replacement_account.save(update_fields=("status",))
        form = ReplacementForm()
        self.assertIn(self.replacement_account, form.fields["original_account"].queryset)

    def test_viewer_can_read_but_cannot_create_replacement(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse("replacements:list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("replacements:create")).status_code, 403)

    def test_replacement_contains_no_customer_identity_fields(self):
        field_names = {field.name for field in Replacement._meta.get_fields()}
        self.assertTrue(
            {"customer", "customer_name", "customer_email", "customer_phone"}.isdisjoint(
                field_names
            )
        )
