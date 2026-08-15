from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from inventory.models import DigitalAccount
from services.models import DigitalService


class DashboardAccessTests(TestCase):
    def test_health_endpoint_is_public_and_ready(self) -> None:
        response = self.client.get(reverse("dashboard:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready"})

    def test_anonymous_user_is_redirected_to_login(self) -> None:
        response = self.client.get(reverse("dashboard:home"))
        self.assertRedirects(response, f"{reverse('login')}?next=/")

    def test_authenticated_user_can_open_dashboard(self) -> None:
        user = User.objects.create_user(username="admin", password="Strong-Test-Password-987")
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Control de cuentas digitales")

    def test_dashboard_uses_real_inventory_metrics(self) -> None:
        user = User.objects.create_user(username="seller", password="Strong-Test-Password-987")
        service = DigitalService.objects.create(name="Netflix")
        DigitalAccount.objects.create(
            service=service,
            email="available@example.com",
            status=DigitalAccount.Status.AVAILABLE,
            created_by=user,
        )
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, "Disponibles")
        self.assertContains(response, ">1<", html=False)
        self.assertContains(response, "Inventario por plataforma")
        self.assertContains(response, "service-badge-netflix")
