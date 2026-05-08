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

    def test_x_robots_tag_on_admin_paths(self):
        """Las URLs del admin nunca deben ser indexables por buscadores."""
        # Aunque el admin redirige a login (no autenticado), el middleware
        # ya añadió la cabecera. Eso es defense-in-depth: incluso un 302
        # accidentalmente filtrado en logs no se indexa.
        resp = self.client.get("/panel-jheliz-2026/")
        self.assertEqual(
            resp.headers.get("X-Robots-Tag"), "noindex, nofollow, noarchive"
        )

    def test_x_robots_tag_absent_on_public_pages(self):
        """Las páginas públicas SÍ son indexables (no deben tener noindex)."""
        resp = self.client.get("/")
        self.assertNotIn("X-Robots-Tag", resp.headers)

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


class AuditLogViewerTests(TestCase):
    """Tests del visor de auditoría (`/panel-jheliz-2026/auditoria/`)."""

    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="x",
            is_staff=True,
        )
        self.list_url = reverse("admin_auditlog")

    def _create_log_entry(self, *, action, changes=None, object_repr="Pedido #1"):
        from auditlog.models import LogEntry
        from django.contrib.contenttypes.models import ContentType
        from orders.models import Order

        ct = ContentType.objects.get_for_model(Order)
        return LogEntry.objects.create(
            content_type=ct,
            object_pk="1",
            object_id=1,
            object_repr=object_repr,
            action=action,
            changes=changes or {},
            actor=self.staff,
            remote_addr="10.0.0.1",
        )

    def test_requires_staff(self):
        self.client.logout()
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, 302)  # redirect a login

    def test_list_page_renders_for_staff(self):
        self.client.force_login(self.staff)
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Auditoría")

    def test_list_shows_entry(self):
        from auditlog.models import LogEntry

        entry = self._create_log_entry(
            action=LogEntry.Action.UPDATE,
            changes={"status": ["pending", "paid"]},
            object_repr="Pedido #1234",
        )
        self.client.force_login(self.staff)
        resp = self.client.get(self.list_url)
        self.assertContains(resp, "Pedido #1234")
        self.assertContains(resp, "Editó")
        # El diff aparece en el preview.
        self.assertContains(resp, "status")

    def test_filter_by_action(self):
        from auditlog.models import LogEntry

        self._create_log_entry(
            action=LogEntry.Action.CREATE, object_repr="Crear A",
        )
        self._create_log_entry(
            action=LogEntry.Action.UPDATE, object_repr="Editar B",
        )
        self.client.force_login(self.staff)
        resp = self.client.get(self.list_url + "?action=create")
        self.assertContains(resp, "Crear A")
        self.assertNotContains(resp, "Editar B")

    def test_filter_by_search(self):
        from auditlog.models import LogEntry

        self._create_log_entry(
            action=LogEntry.Action.UPDATE,
            object_repr="Pedido único X",
        )
        self._create_log_entry(
            action=LogEntry.Action.UPDATE,
            object_repr="Otro objeto Y",
        )
        self.client.force_login(self.staff)
        resp = self.client.get(self.list_url + "?q=único")
        self.assertContains(resp, "Pedido único X")
        self.assertNotContains(resp, "Otro objeto Y")

    def test_detail_page(self):
        from auditlog.models import LogEntry

        entry = self._create_log_entry(
            action=LogEntry.Action.UPDATE,
            changes={"status": ["pending", "paid"], "total": ["10.00", "20.00"]},
            object_repr="Pedido #999",
        )
        self.client.force_login(self.staff)
        url = reverse("admin_auditlog_detail", args=[entry.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Pedido #999")
        # El diff aparece en la tabla.
        self.assertContains(resp, "status")
        self.assertContains(resp, "total")
        self.assertContains(resp, "10.00")
        self.assertContains(resp, "20.00")

    def test_detail_404_for_unknown_entry(self):
        self.client.force_login(self.staff)
        url = reverse("admin_auditlog_detail", args=[999999])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_truncation_of_long_values(self):
        """Valores muy largos en `changes` se truncan al renderizar para no romper el layout."""
        from auditlog.models import LogEntry

        long_value = "a" * 500
        entry = self._create_log_entry(
            action=LogEntry.Action.UPDATE,
            changes={"notes": ["", long_value]},
        )
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_auditlog_detail", args=[entry.pk]))
        self.assertEqual(resp.status_code, 200)
        # El truncado del helper limita a 200 chars + elipsis.
        body = resp.content.decode()
        self.assertNotIn(long_value, body)
