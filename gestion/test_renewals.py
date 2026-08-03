from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Client, ControlSettings, RenewalRequest, Service, Subscription, Tenant,
)
from .tenant_views import _international_phone, _renewal_request_for


@override_settings(ROOT_URLCONF="config.urls_jheliztv")
class RenewalWebFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user("renew-owner", password="test")
        tenant = Tenant.objects.create(user=self.owner, business_name="TV Chile")
        tenant.plan_expires_at = timezone.now() + timedelta(days=30)
        tenant.save()
        ControlSettings.objects.create(owner=self.owner, country="CL", currency="CLP")
        self.customer = Client.objects.create(
            owner=self.owner, name="Camila", whatsapp="987654321"
        )
        self.service = Service.objects.create(owner=self.owner, name="Prime Video")
        self.sub = Subscription.objects.create(
            owner=self.owner, client=self.customer, service=self.service,
            account_email="camila@example.com",
            expires_at=timezone.now() + timedelta(days=2),
        )
        self.renewal = _renewal_request_for(self.sub)

    def test_chilean_local_number_gets_country_prefix(self):
        self.assertEqual(_international_phone("987654321", "CL"), "56987654321")
        self.assertEqual(_international_phone("+52 55 1234 5678", "MX"), "525512345678")
        self.assertEqual(_international_phone("912345678", "ES"), "34912345678")
        self.assertEqual(_international_phone("9876543210", "IN"), "919876543210")
        self.assertEqual(_international_phone("09012345678", "JP"), "819012345678")

    def test_public_customer_can_request_renewal_without_login(self):
        response = self.client.post(
            reverse("jheliztv_public_renewal", kwargs={"token": self.renewal.token}),
            {"action": "renew"},
            secure=True,
        )
        self.assertEqual(response.status_code, 302)
        self.renewal.refresh_from_db()
        self.assertEqual(self.renewal.status, RenewalRequest.Status.PAYMENT_PENDING)

    def test_public_page_disables_browser_cache(self):
        response = self.client.get(
            reverse("jheliztv_public_renewal", kwargs={"token": self.renewal.token}),
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
