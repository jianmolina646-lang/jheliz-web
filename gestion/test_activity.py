from django.contrib.auth import get_user_model
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from gestion.models import Tenant, TenantActivity, TenantActivityEvent


@override_settings(SECURE_SSL_REDIRECT=False, ROOT_URLCONF="config.urls_jheliztv")
class ActivityDashboardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="active-tenant", password="safe-password-123"
        )
        self.tenant = Tenant.objects.create(user=self.user)
        self.owner = get_user_model().objects.create_superuser(
            username="panel-owner", password="owner-safe-password-123"
        )

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

    def test_owner_users_page_filters_activity(self):
        owner = get_user_model().objects.create_superuser(
            username="activity-owner", password="owner-safe-password-123"
        )
        self.client.force_login(owner)
        response = self.client.get(
            reverse("jheliztv_control_users"),
            {"q": "active"},
            HTTP_HOST="jheliztv.xyz",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "active-tenant")
        self.assertContains(response, "Usuarios")
        self.assertContains(response, "Actividad")

    def test_owner_users_pagination_sorting_and_status_filters(self):
        self.tenant.plan_expires_at = timezone.now() + timedelta(days=3)
        self.tenant.save(update_fields=["plan_expires_at"])
        for index in range(26):
            user = get_user_model().objects.create_user(username=f"tenant-{index:02d}")
            Tenant.objects.create(
                user=user,
                business_name=f"Negocio {index:02d}",
                plan_expires_at=timezone.now() + timedelta(days=20),
            )
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("jheliztv_control_users"),
            {"estado": "expiring", "orden": "user", "por_pagina": "25"},
            HTTP_HOST="jheliztv.xyz",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["result_count"], 1)
        self.assertContains(response, "active-tenant")
        self.assertContains(response, "Por vencer")

        response = self.client.get(
            reverse("jheliztv_control_users"), {"pagina": 2}, HTTP_HOST="jheliztv.xyz",
        )
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(len(response.context["tenants"]), 2)

    def test_owner_can_export_filtered_users_without_sensitive_fields(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("jheliztv_control_users_export"),
            {"q": "active-tenant"},
            HTTP_HOST="jheliztv.xyz",
        )

        content = response.content.decode("utf-8-sig")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("active-tenant", content)
        self.assertNotIn("password", content.lower())

    def test_owner_bulk_actions_extend_and_block_selected_users_only(self):
        other_user = get_user_model().objects.create_user(username="not-selected")
        other = Tenant.objects.create(
            user=other_user, plan_expires_at=timezone.now() + timedelta(days=5),
        )
        self.tenant.plan_expires_at = timezone.now() + timedelta(days=5)
        self.tenant.save(update_fields=["plan_expires_at"])
        previous_expiry = self.tenant.plan_expires_at
        self.client.force_login(self.owner)

        self.client.post(
            reverse("jheliztv_control_users_bulk_action"),
            {"tenant_ids": [self.tenant.pk], "bulk_action": "extend"},
            HTTP_HOST="jheliztv.xyz",
        )
        self.tenant.refresh_from_db()
        other.refresh_from_db()
        self.assertGreater(self.tenant.plan_expires_at, previous_expiry + timedelta(days=29))
        self.assertLess(other.plan_expires_at, previous_expiry + timedelta(days=6))

        self.client.post(
            reverse("jheliztv_control_users_bulk_action"),
            {"tenant_ids": [self.tenant.pk], "bulk_action": "block"},
            HTTP_HOST="jheliztv.xyz",
        )
        self.tenant.refresh_from_db()
        other.refresh_from_db()
        self.assertTrue(self.tenant.is_blocked)
        self.assertFalse(other.is_blocked)
