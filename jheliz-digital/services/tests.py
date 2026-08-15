from django.test import TestCase
from django.urls import reverse

from accounts.models import User

from .models import DigitalService


class ServiceTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="manager", password="Test-Password-987", role=User.Role.SELLER
        )
        self.viewer = User.objects.create_user(
            username="viewer", password="Test-Password-987", role=User.Role.VIEWER
        )

    def test_slug_is_generated(self):
        service = DigitalService.objects.create(name="Prime Video")
        self.assertEqual(service.slug, "prime-video")

    def test_manager_can_create_service(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("services:create"),
            {"name": "Netflix", "color": "#e50914", "is_active": "on"},
        )
        self.assertRedirects(response, reverse("services:list"))
        self.assertTrue(DigitalService.objects.filter(name="Netflix").exists())

    def test_viewer_can_list_but_cannot_create(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse("services:list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("services:create")).status_code, 403)
