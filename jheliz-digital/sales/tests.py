from cryptography.fernet import Fernet
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from inventory.models import DigitalAccount
from services.models import DigitalService

from .forms import SaleForm
from .models import Sale


@override_settings(ACCOUNT_CREDENTIAL_KEY=Fernet.generate_key().decode("ascii"))
class SaleTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="manager", password="Test-Password-987", role=User.Role.SELLER
        )
        self.viewer = User.objects.create_user(
            username="viewer", password="Test-Password-987", role=User.Role.VIEWER
        )
        self.service = DigitalService.objects.create(name="Netflix")
        self.account = DigitalAccount.objects.create(
            service=self.service,
            email="cuenta@example.com",
            created_by=self.manager,
            status=DigitalAccount.Status.AVAILABLE,
        )

    def sale_data(self, account=None):
        return {
            "account": (account or self.account).pk,
            "amount": "35.90",
            "payment_method": Sale.PaymentMethod.YAPE,
            "payment_reference": "Operacion 123456",
            "sold_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "notes": "Venta interna",
        }

    def test_manager_registers_anonymous_sale_and_account_becomes_sold(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("sales:create"), self.sale_data())
        sale = Sale.objects.get(account=self.account)
        self.assertRedirects(response, reverse("sales:detail", args=[sale.pk]))
        self.account.refresh_from_db()
        self.assertEqual(self.account.status, DigitalAccount.Status.SOLD)
        self.assertEqual(sale.created_by, self.manager)

    def test_sold_account_is_not_offered_again(self):
        self.account.status = DigitalAccount.Status.SOLD
        self.account.save(update_fields=("status",))
        form = SaleForm()
        self.assertNotIn(self.account, form.fields["account"].queryset)

    def test_viewer_can_read_sales_but_cannot_register_one(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse("sales:list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("sales:create")).status_code, 403)

    def test_card_reference_rejects_more_than_four_digits(self):
        sale = Sale(
            account=self.account,
            amount="35.90",
            payment_method=Sale.PaymentMethod.CARD,
            payment_reference="Visa 4111111111111111",
            created_by=self.manager,
        )
        with self.assertRaises(ValidationError):
            sale.full_clean()

    def test_sale_contains_no_customer_identity_fields(self):
        field_names = {field.name for field in Sale._meta.get_fields()}
        self.assertTrue(
            {"customer", "customer_name", "customer_email", "customer_phone"}.isdisjoint(
                field_names
            )
        )
