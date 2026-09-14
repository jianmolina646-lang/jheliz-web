from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from .flow_payments import _signed
from .models import SaasSettings, Tenant, TenantPayment


@override_settings(
    FLOW_API_KEY="api-test", FLOW_SECRET_KEY="secret-test",
    FLOW_API_URL="https://sandbox.flow.cl/api", FLOW_PAYMENT_METHOD="77",
)
class FlowPaymentTests(TestCase):
    host = "jheliztv.xyz"

    def setUp(self):
        user = get_user_model().objects.create_user("flow-user", "flow@example.com", "pass12345")
        self.tenant = Tenant.objects.create(user=user, business_name="Flow Test")
        self.client.force_login(user)
        SaasSettings.load()

    def test_signature_is_sorted_hmac(self):
        signed = _signed({"token": "abc", "apiKey": "api-test"})
        self.assertEqual(len(signed["s"]), 64)
        self.assertEqual(signed["apiKey"], "api-test")

    @patch("gestion.tenant_views.create_payment")
    def test_create_redirects_to_flow_and_stores_order(self, create):
        create.return_value = {"url": "https://sandbox.flow.cl/app/web/pay.php", "token": "tok-1", "flowOrder": 123}
        response = self.client.post("/pagos/flow/crear/", {"payer_email": "payer@example.com"}, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("https://sandbox.flow.cl/"))
        payment = TenantPayment.objects.get(tenant=self.tenant)
        self.assertEqual(payment.method, TenantPayment.Method.FLOW_QR)
        self.assertEqual(payment.provider_token, "tok-1")

    @patch("gestion.tenant_views.create_payment")
    def test_create_requires_real_email(self, create):
        response = self.client.post("/pagos/flow/crear/", {"payer_email": "correo-invalido"}, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 302)
        create.assert_not_called()
        self.assertFalse(TenantPayment.objects.exists())

    @patch("gestion.tenant_views.get_status")
    def test_callback_approves_once(self, status):
        payment = TenantPayment.objects.create(
            tenant=self.tenant, method=TenantPayment.Method.FLOW_QR,
            amount=Decimal("30.00"), days=30, provider_order_id="JC-1-test",
            provider_token="tok-paid",
        )
        status.return_value = {
            "status": 2, "commerceOrder": "JC-1-test", "amount": 30,
            "flowOrder": 456, "currency": "PEN",
        }
        before = self.tenant.plan_expires_at or timezone.now()
        first = self.client.post("/pagos/flow/confirmacion/", {"token": "tok-paid"}, HTTP_HOST=self.host)
        second = self.client.post("/pagos/flow/confirmacion/", {"token": "tok-paid"}, HTTP_HOST=self.host)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        payment.refresh_from_db(); self.tenant.refresh_from_db()
        self.assertEqual(payment.status, TenantPayment.Status.APPROVED)
        self.assertGreater(self.tenant.plan_expires_at, before)
        expiry = self.tenant.plan_expires_at
        self.client.post("/pagos/flow/confirmacion/", {"token": "tok-paid"}, HTTP_HOST=self.host)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.plan_expires_at, expiry)

    @patch("gestion.tenant_views.get_status")
    def test_callback_rejects_amount_mismatch(self, status):
        TenantPayment.objects.create(
            tenant=self.tenant, method=TenantPayment.Method.FLOW_QR,
            amount=Decimal("30.00"), provider_order_id="JC-2-test", provider_token="tok-bad",
        )
        status.return_value = {"status": 2, "commerceOrder": "JC-2-test", "amount": 1, "flowOrder": 9}
        response = self.client.post("/pagos/flow/confirmacion/", {"token": "tok-bad"}, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(TenantPayment.objects.get(provider_token="tok-bad").status, TenantPayment.Status.PENDING)

    def test_billing_can_resume_pending_flow_checkout(self):
        TenantPayment.objects.create(
            tenant=self.tenant, method=TenantPayment.Method.FLOW_QR,
            amount=Decimal("30.00"), provider_order_id="JC-resume",
            provider_token="tok-resume",
            provider_payload={"url": "https://www.flow.cl/app/web/pay.php"},
        )
        response = self.client.get("/suscripcion/", HTTP_HOST=self.host)
        self.assertContains(response, "Continuar pago en Flow")
        self.assertContains(response, "https://www.flow.cl/app/web/pay.php?token=tok-resume")
