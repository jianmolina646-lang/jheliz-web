from datetime import timedelta

from cryptography.fernet import Fernet
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from services.models import DigitalService

from .forms import DigitalAccountForm
from .models import DigitalAccount


TEST_CREDENTIAL_KEY = Fernet.generate_key().decode("ascii")


@override_settings(ACCOUNT_CREDENTIAL_KEY=TEST_CREDENTIAL_KEY)
class DigitalAccountTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="manager", password="Test-Password-987", role=User.Role.ADMIN
        )
        self.viewer = User.objects.create_user(
            username="viewer", password="Test-Password-987", role=User.Role.VIEWER
        )
        self.service = DigitalService.objects.create(name="Netflix", color="#e50914")

    def create_account(self, **changes):
        values = {
            "service": self.service,
            "email": "cuenta@example.com",
            "created_by": self.manager,
            "renewal_date": timezone.localdate() + timedelta(days=10),
        }
        values.update(changes)
        account = DigitalAccount(**values)
        account.set_password("Clave-no-visible-123")
        account.save()
        return account

    def test_password_is_encrypted_and_can_be_recovered_by_model(self):
        account = self.create_account()
        self.assertNotIn("Clave-no-visible-123", account.encrypted_password)
        self.assertEqual(account.get_password(), "Clave-no-visible-123")

    def test_email_is_normalized(self):
        account = self.create_account(email="  Cuenta@Example.COM ")
        self.assertEqual(account.email, "cuenta@example.com")

    def test_full_card_number_is_rejected(self):
        account = self.create_account()
        account.billing_reference = "Visa 4111111111111111"
        with self.assertRaises(ValidationError):
            account.full_clean()

    def test_manager_can_create_account_without_plaintext_storage(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("inventory:create"),
            {
                "service": self.service.pk,
                "email": "Nueva@Example.com",
                "password": "Otra-Clave-456",
                "status": DigitalAccount.Status.AVAILABLE,
                "acquisition_cost": "20.00",
                "billing_method": DigitalAccount.BillingMethod.CARD,
                "billing_reference": "Visa 1234",
                "country": "Perú",
                "notes": "Cuenta completa",
            },
        )
        account = DigitalAccount.objects.get(email="nueva@example.com")
        self.assertRedirects(response, reverse("inventory:detail", args=[account.pk]))
        self.assertNotIn("Otra-Clave-456", account.encrypted_password)

    def test_blank_password_on_edit_preserves_encrypted_value(self):
        account = self.create_account()
        encrypted_value = account.encrypted_password
        form = DigitalAccountForm(
            {
                "service": self.service.pk,
                "email": account.email,
                "password": "",
                "status": account.status,
                "acquisition_cost": account.acquisition_cost,
                "billing_method": account.billing_method,
                "billing_reference": "",
                "country": "Perú",
                "notes": "Actualizada",
            },
            instance=account,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        account.refresh_from_db()
        self.assertEqual(account.encrypted_password, encrypted_value)

    def test_viewer_can_read_but_cannot_write(self):
        account = self.create_account()
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse("inventory:list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("inventory:detail", args=[account.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("inventory:create")).status_code, 403)
        self.assertEqual(self.client.get(reverse("inventory:update", args=[account.pk])).status_code, 403)

    def test_list_filters_by_service_and_status(self):
        self.create_account(status=DigitalAccount.Status.AVAILABLE)
        other = DigitalService.objects.create(name="Disney Plus")
        self.create_account(
            service=other,
            email="otra@example.com",
            status=DigitalAccount.Status.SOLD,
        )
        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse("inventory:list"),
            {"service": self.service.slug, "status": DigitalAccount.Status.AVAILABLE},
        )
        self.assertContains(response, "cu••••@example.com")
        self.assertNotContains(response, "otra@example.com")

    def test_inventory_is_ordered_by_platform_and_email(self):
        prime = DigitalService.objects.create(name="Prime Video")
        self.create_account(email="zeta@example.com")
        self.create_account(email="alfa@example.com", service=prime)
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("inventory:list"))
        accounts = list(response.context["accounts"])
        self.assertEqual(
            [(account.service.name, account.email) for account in accounts],
            [("Netflix", "zeta@example.com"), ("Prime Video", "alfa@example.com")],
        )
        self.assertContains(response, "service-badge-netflix")
        self.assertContains(response, "service-badge-prime-video")

    def test_account_list_exposes_real_summary_and_new_layout(self):
        self.create_account(status=DigitalAccount.Status.AVAILABLE)
        self.create_account(
            email="vendida@example.com",
            status=DigitalAccount.Status.SOLD,
        )
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("inventory:list"))
        self.assertEqual(response.context["summary"]["total"], 2)
        self.assertEqual(response.context["summary"]["available"], 1)
        self.assertEqual(response.context["summary"]["sold"], 1)
        self.assertContains(response, "Inventario de cuentas")
        self.assertContains(response, "status-available")
        self.assertContains(response, "status-sold")

    def test_account_list_filters_renewals_and_paginates(self):
        today = timezone.localdate()
        self.create_account(email="vencida@example.com", renewal_date=today - timedelta(days=2))
        self.create_account(email="vigente@example.com", renewal_date=today + timedelta(days=20))
        DigitalAccount.objects.bulk_create(
            [
                DigitalAccount(
                    service=self.service,
                    email=f"pagina-{index}@example.com",
                    created_by=self.manager,
                )
                for index in range(20)
            ]
        )
        self.client.force_login(self.viewer)
        overdue = self.client.get(reverse("inventory:list"), {"renewal": "overdue"})
        self.assertEqual(overdue.context["result_count"], 1)
        self.assertContains(overdue, "vencida hace 2 días")
        page_two = self.client.get(reverse("inventory:list"), {"page": 2})
        self.assertEqual(page_two.context["page_obj"].paginator.num_pages, 2)
        self.assertEqual(page_two.context["page_obj"].number, 2)

    def test_summary_reports_overdue_and_featured_counts(self):
        today = timezone.localdate()
        self.create_account(email="vencida@example.com", renewal_date=today - timedelta(days=2))
        self.create_account(email="destacada@example.com", is_featured=True)
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("inventory:list"))
        self.assertEqual(response.context["summary"]["overdue"], 1)
        self.assertEqual(response.context["summary"]["featured"], 1)

    def test_list_filters_by_featured(self):
        self.create_account(email="destacada@example.com", is_featured=True)
        self.create_account(email="normal@example.com", is_featured=False)
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("inventory:list"), {"featured": "1"})
        self.assertEqual(response.context["result_count"], 1)
        self.assertContains(response, "de•••••••@example.com")
        self.assertNotContains(response, "no••••@example.com")

    def test_manager_can_toggle_featured_and_preserves_query(self):
        account = self.create_account()
        self.assertFalse(account.is_featured)
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("inventory:toggle_featured", args=[account.pk]),
            {"next_query": "status=available"},
        )
        account.refresh_from_db()
        self.assertTrue(account.is_featured)
        self.assertRedirects(response, f"{reverse('inventory:list')}?status=available")

        response = self.client.post(reverse("inventory:toggle_featured", args=[account.pk]))
        account.refresh_from_db()
        self.assertFalse(account.is_featured)
        self.assertRedirects(response, reverse("inventory:list"))

    def test_toggle_featured_requires_post(self):
        account = self.create_account()
        self.client.force_login(self.manager)
        response = self.client.get(reverse("inventory:toggle_featured", args=[account.pk]))
        self.assertEqual(response.status_code, 405)

    def test_viewer_cannot_toggle_featured(self):
        account = self.create_account()
        self.client.force_login(self.viewer)
        response = self.client.post(reverse("inventory:toggle_featured", args=[account.pk]))
        self.assertEqual(response.status_code, 403)
        account.refresh_from_db()
        self.assertFalse(account.is_featured)
