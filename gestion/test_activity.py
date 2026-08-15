from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from gestion.models import Tenant, TenantActivity, TenantActivityEvent


@override_settings(SECURE_SSL_REDIRECT=False, ROOT_URLCONF="config.urls_jheliztv")
class ActivityDashboardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="active-tenant", password="safe-password-123"
        )
        self.tenant = Tenant.objects.create(user=self.user)

    def test_tenant_request_updates_activity_without_touching_business_data(self):
        self.client.force_login(self.user)
        response = self.client.get("/app/", HTTP_HOST="jheliztv.xyz")
        self.assertIn(response.status_code, (200, 302))
        activity = TenantActivity.objects.get(tenant=self.tenant)
        self.assertEqual(activity.total_requests, 1)
        self.assertEqual(activity.last_path, "/app/")

    def test_successful_post_records_sanitized_action_only(self):
        self.client.force_login(self.user)
        self.client.post(
            "/app/movimientos/agregar/",
            {"description": "private-value", "amount": "1"},
            HTTP_HOST="jheliztv.xyz",
        )
        event = TenantActivityEvent.objects.get(tenant=self.tenant)
        self.assertNotIn("private-value", event.path)
        self.assertEqual(event.action, "movimiento_creado")

    def test_owner_dashboard_filters_activity(self):
        owner = get_user_model().objects.create_superuser(
            username="activity-owner", password="owner-safe-password-123"
        )
        self.client.force_login(owner)
        response = self.client.get(
            reverse("jheliztv_control_dashboard"),
            {"actividad": "inactivos", "q": "active"},
            HTTP_HOST="jheliztv.xyz",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "active-tenant")
        self.assertContains(response, "Actividad de usuarios")
