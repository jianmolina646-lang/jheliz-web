from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from catalog.models import Category, Plan, Product, ProductMode


class MarketingDomainTests(TestCase):
    host = "marketingjhelizxyz.online"

    def setUp(self):
        category = Category.objects.create(name="Streaming mayorista", audience="distribuidor")
        self.complete = Product.objects.create(
            category=category,
            name="Cuenta completa",
            mode=ProductMode.COMPLETA,
            delivery_is_instant=True,
            is_active=True,
        )
        Plan.objects.create(
            product=self.complete,
            name="30 dias",
            price_customer=Decimal("20.00"),
            price_distributor=Decimal("12.00"),
            available_for_distributor=True,
        )
        profile = Product.objects.create(
            category=category,
            name="Perfil compartido",
            mode=ProductMode.PERFIL,
            delivery_is_instant=True,
            is_active=True,
        )
        Plan.objects.create(
            product=profile,
            name="30 dias",
            price_customer=Decimal("10.00"),
            price_distributor=Decimal("6.00"),
            available_for_distributor=True,
        )

    def test_home_only_shows_complete_accounts(self):
        response = self.client.get("/", HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "marketing/home.html")
        self.assertContains(response, "Cuenta completa")
        self.assertNotContains(response, "Perfil compartido")
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow, noarchive")

    def test_signup_creates_regular_customer(self):
        response = self.client.post(
            "/cuenta/registro/",
            {
                "username": "mayorista",
                "email": "mayorista@example.com",
                "phone": "978640413",
                "telegram_username": "",
                "role": "cliente",
                "password1": "A-password-very-safe-2026",
                "password2": "A-password-very-safe-2026",
            },
            HTTP_HOST=self.host,
        )
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username="mayorista")
        self.assertEqual(user.role, "cliente")
        self.assertFalse(user.distributor_approved)

    def test_anonymous_buyer_can_open_store(self):
        response = self.client.get("/productos/", HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cuenta completa")
        self.assertNotContains(response, "Perfil compartido")

    def test_www_redirects_to_canonical_host(self):
        response = self.client.get("/ruta/?x=1", HTTP_HOST="www.marketingjhelizxyz.online")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, "https://marketingjhelizxyz.online/ruta/?x=1")
