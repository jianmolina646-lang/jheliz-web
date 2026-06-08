"""Tests de Jheliz Control: modelos (utilidad, semáforo, contador, renovar),
vistas (render + acciones) y reporte PDF."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Client,
    ControlSettings,
    Service,
    ServiceCategory,
    Subscription,
    Transaction,
)


class ModelLogicTests(TestCase):
    def setUp(self):
        self.cat = ServiceCategory.objects.create(name="TV", slug="tv")
        self.svc = Service.objects.create(name="Disney+", category=self.cat)
        self.cli = Client.objects.create(name="Juan", telegram="juan", whatsapp="+51 987 654 321")

    def _sub(self, **kw):
        defaults = dict(
            client=self.cli, service=self.svc, account_email="a@b.com",
            cost=Decimal("15.00"), investment=Decimal("5.00"),
            expires_at=timezone.now() + timedelta(days=10),
        )
        defaults.update(kw)
        return Subscription.objects.create(**defaults)

    def test_profit(self):
        self.assertEqual(self._sub().profit, Decimal("10.00"))

    def test_status_green(self):
        self.assertEqual(self._sub(expires_at=timezone.now() + timedelta(days=5)).status_color, "green")

    def test_status_yellow(self):
        self.assertEqual(self._sub(expires_at=timezone.now() + timedelta(days=2)).status_color, "yellow")

    def test_status_red(self):
        self.assertEqual(self._sub(expires_at=timezone.now() + timedelta(hours=3)).status_color, "red")

    def test_status_expired(self):
        s = self._sub(expires_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(s.status_color, "expired")
        self.assertTrue(s.is_expired)
        self.assertEqual(s.time_left_label, "Vencida")

    def test_renew_accumulates(self):
        s = self._sub(expires_at=timezone.now() + timedelta(days=5))
        before = s.expires_at
        s.renew(30)
        self.assertAlmostEqual((s.expires_at - before).days, 30, delta=1)

    def test_renew_from_now_when_expired(self):
        s = self._sub(expires_at=timezone.now() - timedelta(days=2))
        s.renew(30)
        self.assertGreater(s.seconds_left, 28 * 86400)

    def test_telegram_normalized(self):
        c = Client.objects.create(name="X", telegram="pepe")
        self.assertEqual(c.telegram, "@pepe")
        self.assertEqual(c.telegram_handle, "pepe")

    def test_whatsapp_digits(self):
        self.assertEqual(self.cli.whatsapp_digits, "51987654321")

    def test_settings_singleton(self):
        a = ControlSettings.load()
        b = ControlSettings.load()
        self.assertEqual(a.pk, b.pk)


class ViewTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.user = U.objects.create_user("admin", password="pw", is_staff=True, is_superuser=True)
        self.client.force_login(self.user)
        self.cat = ServiceCategory.objects.create(name="TV", slug="tv")
        self.svc = Service.objects.create(name="Disney+", category=self.cat)
        self.cli = Client.objects.create(name="Juan", telegram="juan", whatsapp="+51987654321")
        self.sub = Subscription.objects.create(
            client=self.cli, service=self.svc, account_email="a@b.com",
            account_password="secret", cost=Decimal("15"), investment=Decimal("5"),
            expires_at=timezone.now() + timedelta(days=2),
        )

    def test_pages_render(self):
        for name, args in [
            ("gestion_dashboard", []),
            ("gestion_services", []),
            ("gestion_service_detail", [self.svc.pk]),
            ("gestion_clients", []),
            ("gestion_search", []),
        ]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)

    def test_search_finds_by_email(self):
        r = self.client.get(reverse("gestion_search"), {"q": "a@b.com"})
        self.assertContains(r, "Juan")

    def test_notifications_json(self):
        r = self.client.get(reverse("gestion_notifications"))
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["count"], 1)

    def test_add_client(self):
        r = self.client.post(reverse("gestion_client_add"),
                             {"name": "Maria", "telegram": "maria"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Client.objects.filter(name="Maria").exists())

    def test_add_subscription_creates_transactions(self):
        r = self.client.post(reverse("gestion_subscription_add"), {
            "service": self.svc.pk, "client": self.cli.pk, "account_email": "x@y.com",
            "plan": "perfil", "profiles": "2", "cost": "20", "investment": "8",
            "duration_days": "30",
        })
        self.assertEqual(r.status_code, 302)
        s = Subscription.objects.get(account_email="x@y.com")
        self.assertTrue(s.transactions.filter(kind="income").exists())
        self.assertTrue(s.transactions.filter(kind="expense").exists())

    def test_renew_view(self):
        before = self.sub.expires_at
        self.client.post(reverse("gestion_subscription_renew", args=[self.sub.pk]), {"days": "30"})
        self.sub.refresh_from_db()
        self.assertGreater(self.sub.expires_at, before)

    def test_edit_preserves_expiry(self):
        before = self.sub.expires_at
        self.client.post(reverse("gestion_subscription_edit", args=[self.sub.pk]), {
            "service": self.svc.pk, "client": self.cli.pk, "account_email": "new@y.com",
            "plan": "completa", "profiles": "1", "cost": "30", "investment": "5",
        })
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.account_email, "new@y.com")
        self.assertAlmostEqual((self.sub.expires_at - before).total_seconds(), 0, delta=5)

    def test_client_report_pdf(self):
        r = self.client.get(reverse("gestion_client_report", args=[self.cli.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))

    def test_requires_staff(self):
        self.client.logout()
        r = self.client.get(reverse("gestion_dashboard"))
        self.assertIn(r.status_code, (301, 302))
