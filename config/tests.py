"""Tests para el PR B — cabeceras de seguridad y endpoint del bell de notificaciones."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


class SecurityHeadersTests(TestCase):
    def test_csp_header_present(self):
        resp = self.client.get("/")
        self.assertIn("Content-Security-Policy", resp.headers)
        csp = resp.headers["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("object-src 'none'", csp)

    def test_permissions_policy_present(self):
        resp = self.client.get("/")
        self.assertIn("Permissions-Policy", resp.headers)
        pp = resp.headers["Permissions-Policy"]
        self.assertIn("camera=()", pp)
        self.assertIn("microphone=()", pp)
        self.assertIn("geolocation=()", pp)

    def test_referrer_policy(self):
        resp = self.client.get("/")
        self.assertEqual(
            resp.headers.get("Referrer-Policy"),
            "strict-origin-when-cross-origin",
        )

    def test_x_frame_options_deny(self):
        resp = self.client.get("/")
        self.assertEqual(resp.headers.get("X-Frame-Options"), "DENY")

    def test_x_content_type_options_nosniff(self):
        resp = self.client.get("/")
        self.assertEqual(
            resp.headers.get("X-Content-Type-Options"), "nosniff"
        )

    def test_coop_corp_set(self):
        resp = self.client.get("/")
        self.assertEqual(
            resp.headers.get("Cross-Origin-Opener-Policy"), "same-origin"
        )
        self.assertEqual(
            resp.headers.get("Cross-Origin-Resource-Policy"), "same-origin"
        )

    @override_settings(DEBUG=False, SECURE_HSTS_SECONDS=31536000, SECURE_HSTS_PRELOAD=True, SECURE_HSTS_INCLUDE_SUBDOMAINS=True)
    def test_hsts_preload_in_prod(self):
        # SecurityMiddleware sólo escribe HSTS sobre HTTPS; simulamos:
        resp = self.client.get("/", secure=True)
        sts = resp.headers.get("Strict-Transport-Security", "")
        self.assertIn("max-age=31536000", sts)
        self.assertIn("includeSubDomains", sts)
        self.assertIn("preload", sts)


class NotificationsBellEndpointTests(TestCase):
    """Tests del endpoint que alimenta el bell del admin (lista de pendientes)."""

    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="admin", email="admin@example.com", password="x"
        )
        self.staff.is_staff = True
        self.staff.save()
        self.client.force_login(self.staff)
        self.url = reverse("admin_notifications_count")

    def _create_yape_order(self, *, total: str = "49.90", email: str = "buyer@example.com"):
        from orders.models import Order

        return Order.objects.create(
            email=email,
            phone="+51999000111",
            status=Order.Status.VERIFYING,
            total=Decimal(total),
            currency="PEN",
            payment_provider="yape",
        )

    def test_requires_staff(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)  # redirect a login

    def test_empty_state_returns_zero_counts_and_empty_items(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["verifying"], 0)
        self.assertEqual(data["preparing"], 0)
        self.assertEqual(data["open_tickets"], 0)
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["items"], [])
        # Compat con el JS viejo del dashboard.
        self.assertEqual(data["counts"]["total"], 0)

    def test_verifying_yape_order_appears_in_items(self):
        order = self._create_yape_order(email="comprador@example.com")
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["verifying"], 1)
        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["items"]), 1)

        item = data["items"][0]
        self.assertEqual(item["id"], f"order-verifying-{order.pk}")
        self.assertEqual(item["kind"], "yape_proof")
        # Título contiene short uuid + monto.
        self.assertIn(order.short_uuid, item["title"])
        self.assertIn("49.90", item["title"])
        # Subtítulo lleva el correo del cliente para identificarlo de un vistazo.
        self.assertIn("comprador@example.com", item["subtitle"])
        # URL apunta al detalle del pedido en el admin.
        self.assertEqual(
            item["url"],
            reverse("admin:orders_order_change", args=[order.pk]),
        )
        # `relative` es un string corto en español.
        self.assertTrue(item["relative"].startswith("hace"))

    def test_items_sorted_most_recent_first(self):
        from orders.models import Order
        from django.utils import timezone
        from datetime import timedelta

        old = self._create_yape_order(email="viejo@x.com")
        new = self._create_yape_order(email="nuevo@x.com")
        # Forzamos timestamps de subida del comprobante: `old` antes, `new` después.
        Order.objects.filter(pk=old.pk).update(
            payment_proof_uploaded_at=timezone.now() - timedelta(hours=2)
        )
        Order.objects.filter(pk=new.pk).update(
            payment_proof_uploaded_at=timezone.now() - timedelta(minutes=5)
        )

        resp = self.client.get(self.url)
        data = resp.json()
        ids = [it["id"] for it in data["items"]]
        self.assertEqual(
            ids,
            [f"order-verifying-{new.pk}", f"order-verifying-{old.pk}"],
        )

    def test_preparing_orders_also_listed(self):
        from orders.models import Order

        order = Order.objects.create(
            email="x@x.com",
            status=Order.Status.PREPARING,
            total=Decimal("100.00"),
            currency="PEN",
            payment_provider="mercadopago",
        )
        resp = self.client.get(self.url)
        data = resp.json()
        self.assertEqual(data["preparing"], 1)
        kinds = {it["kind"] for it in data["items"]}
        self.assertIn("preparing", kinds)
        # El título lleva la palabra "preparación" (con tilde, como aparece en UI).
        prep = [it for it in data["items"] if it["id"] == f"order-preparing-{order.pk}"][0]
        self.assertIn("preparación", prep["title"])

    def test_resolved_tickets_excluded_from_items(self):
        from support.models import Ticket

        Ticket.objects.create(
            user=self.staff,
            subject="Ya estaba resuelto",
            status=Ticket.Status.RESOLVED,
        )
        Ticket.objects.create(
            user=self.staff,
            subject="Tengo problemas con mi cuenta de Netflix",
            status=Ticket.Status.OPEN,
        )
        resp = self.client.get(self.url)
        data = resp.json()
        self.assertEqual(data["open_tickets"], 1)
        ticket_items = [it for it in data["items"] if it["kind"] == "ticket"]
        self.assertEqual(len(ticket_items), 1)
        self.assertIn("Netflix", ticket_items[0]["title"])
