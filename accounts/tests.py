"""Tests para el PR C — rendimiento (N+1, queries del admin)."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse

from accounts.models import Role
from orders.models import Order


User = get_user_model()


def _query_count(client, url):
    with CaptureQueriesContext(connection) as ctx:
        resp = client.get(url)
    return resp, len(ctx.captured_queries)


class CustomerAdminQueryTests(TestCase):
    """El N+1 clásico: una columna como last_order_at no debe disparar
    una query por fila del listado.
    """

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="password",
        )
        for i in range(10):
            customer = User.objects.create_user(
                username=f"cliente{i}", email=f"c{i}@e.com",
                password="x", role=Role.CLIENTE,
            )
            for _ in range(3):
                Order.objects.create(
                    user=customer, email=customer.email,
                    total=Decimal("10.00"), status=Order.Status.DELIVERED,
                )

    def test_customer_changelist_does_not_scale_with_rows(self):
        """Antes: ~10+ queries adicionales (una por cliente para last_order_at).
        Ahora: la query base no escala con N clientes."""
        self.client.force_login(self.staff)
        url = reverse("admin:accounts_customer_changelist")
        resp, n = _query_count(self.client, url)
        self.assertEqual(resp.status_code, 200)
        # Tope holgado: con N+1 (10 customers) sería >20.
        self.assertLess(
            n, 20,
            f"Sospecha de N+1 en CustomerAdmin: {n} queries para 10 clientes "
            "con 3 pedidos cada uno.",
        )


class DashboardQueryTests(TestCase):
    """El dashboard hacía N queries .exists() (una por cliente del mes)
    para distinguir nuevos vs recurrentes. Ahora es una sola agregación.
    """

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="password",
        )
        for i in range(15):
            customer = User.objects.create_user(
                username=f"u{i}", email=f"u{i}@e.com", password="x",
                role=Role.CLIENTE,
            )
            Order.objects.create(
                user=customer, email=customer.email,
                total=Decimal("20.00"), status=Order.Status.DELIVERED,
            )

    def test_dashboard_does_not_scale_with_customers(self):
        """Antes: 15+ queries .exists() en el bucle de nuevos vs recurrentes.
        Ahora: una sola query agregada."""
        self.client.force_login(self.staff)
        resp, n = _query_count(self.client, "/jheliz-admin/")
        self.assertEqual(resp.status_code, 200)
        # Tope holgado para no romperse con cambios cosméticos en Unfold.
        self.assertLess(
            n, 50,
            f"Sospecha de N+1 en dashboard_callback: {n} queries con 15 clientes.",
        )


class DeliverViewAtomicityTests(TestCase):
    """Garantía de atomicidad: si algo falla durante la entrega, no se queda
    el pedido a medias (parte de los items con creds, parte sin)."""

    def test_atomic_block_present(self):
        # Test estructural: confirmar que la vista usa transaction.atomic.
        from orders.admin import OrderAdmin
        import inspect
        src = inspect.getsource(OrderAdmin.deliver_view)
        self.assertIn("transaction.atomic", src)
        self.assertIn("on_commit", src)


# -- Password reset --------------------------------------------------------

from django.core import mail
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


class PasswordResetFlowTests(TestCase):
    """End-to-end del flujo: pedir reset, recibir email, abrir link, cambiar
    contraseña, ingresar con la nueva."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="distri",
            email="distri@example.com",
            password="vieja-pass-123",
            role=Role.DISTRIBUIDOR,
        )

    def test_request_form_renders(self):
        resp = self.client.get(reverse("accounts:password_reset"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Recuperar contraseña")

    def test_request_for_existing_email_sends_mail(self):
        resp = self.client.post(
            reverse("accounts:password_reset"),
            {"email": "distri@example.com"},
        )
        self.assertRedirects(resp, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn("distri@example.com", msg.to)
        self.assertIn("/cuenta/recuperar/", msg.body)

    def test_request_for_unknown_email_does_not_enumerate(self):
        """Aunque el email no existe, la respuesta es la misma (302 → done).
        No se manda correo. Esto evita que un atacante pueda enumerar usuarios."""
        resp = self.client.post(
            reverse("accounts:password_reset"),
            {"email": "nadie@example.com"},
        )
        self.assertRedirects(resp, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def _build_confirm_url(self, user):
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        return reverse(
            "accounts:password_reset_confirm",
            kwargs={"uidb64": uidb64, "token": token},
        )

    def test_valid_token_lets_user_set_new_password(self):
        confirm_url = self._build_confirm_url(self.user)
        # GET con token válido → redirige a la URL "set-password" que ya no
        # contiene el token (mejor práctica de Django).
        resp = self.client.get(confirm_url)
        self.assertEqual(resp.status_code, 302)
        set_url = resp["Location"]
        # POST con la pass nueva.
        resp = self.client.post(
            set_url,
            {"new_password1": "nueva-pass-xyz-789", "new_password2": "nueva-pass-xyz-789"},
        )
        self.assertRedirects(resp, reverse("accounts:password_reset_complete"))
        # Login con la nueva pass funciona.
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("nueva-pass-xyz-789"))
        self.assertFalse(self.user.check_password("vieja-pass-123"))

    def test_tampered_token_rejected(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        # Token claramente inválido.
        bad_url = reverse(
            "accounts:password_reset_confirm",
            kwargs={"uidb64": uidb64, "token": "deadbeef-not-a-real-token"},
        )
        resp = self.client.get(bad_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Enlace no válido")

    def test_token_one_use_after_password_change(self):
        """Una vez que se cambia la pass, el token vencido por make_token no
        debe permitir un segundo cambio (Django invalida tokens cuando cambia
        el hash de la pass)."""
        confirm_url = self._build_confirm_url(self.user)
        resp = self.client.get(confirm_url, follow=True)
        self.assertEqual(resp.status_code, 200)
        # Cambiar la pass primera vez.
        set_url = self.client.session["_password_reset_token"]
        # No queremos depender de la URL interna; usamos el redirect previo.
        resp = self.client.get(confirm_url)
        set_url = resp["Location"]
        self.client.post(
            set_url,
            {"new_password1": "primera-nueva-789", "new_password2": "primera-nueva-789"},
        )
        # Re-usar el token original tras cambio de pass → enlace inválido.
        resp = self.client.get(confirm_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Enlace no válido")

    def test_login_link_visible_on_login_page(self):
        resp = self.client.get(reverse("accounts:login"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "¿Olvidaste tu contraseña?")
        self.assertContains(resp, reverse("accounts:password_reset"))


# -- Rediseño moderno admin de Usuarios / Clientes / Distribuidores --------

from datetime import timedelta
from django.utils import timezone

from accounts.admin_helpers import (
    avatar_html,
    chip,
    chips,
    contact_actions,
    modern_table,
    stat_grid,
    time_ago,
    user_card_cell,
    _initials,
    _avatar_colors,
)


class AdminHelpersTests(TestCase):
    """Cubre los helpers visuales del admin de usuarios."""

    def test_initials_from_full_name(self):
        u = User(first_name="Jheliz", last_name="Servicios", username="jhz")
        self.assertEqual(_initials(u), "JS")

    def test_initials_fallback_username(self):
        u = User(username="colocha", email="")
        self.assertEqual(_initials(u), "CO")

    def test_initials_handles_dots_and_underscores(self):
        u = User(username="jian.molina", first_name="", last_name="")
        self.assertEqual(_initials(u), "JM")

    def test_avatar_colors_are_deterministic(self):
        a = _avatar_colors("foo@bar.com")
        b = _avatar_colors("foo@bar.com")
        self.assertEqual(a, b)

    def test_avatar_colors_differ_for_different_seeds(self):
        a = _avatar_colors("a@b.com")
        b = _avatar_colors("c@d.com")
        # No exigimos que SIEMPRE difieran (hash colisiones), pero al menos
        # una pareja debe diferir entre 8 colores.
        seen = set()
        for seed in ("a@b.com", "c@d.com", "x@y.com", "z@w.com"):
            seen.add(_avatar_colors(seed))
        self.assertGreater(len(seen), 1)

    def test_user_card_cell_includes_name_and_sub(self):
        u = User(username="jian", email="jian@x.com", first_name="Jian", last_name="Molina")
        html = str(user_card_cell(u))
        self.assertIn("Jian Molina", html)
        self.assertIn("jian@x.com", html)
        self.assertIn("jh-avatar", html)

    def test_user_card_cell_escapes_html(self):
        u = User(username="<script>", email="<x>@evil.com")
        html = str(user_card_cell(u))
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_chip_renders_with_tone_and_icon(self):
        html = str(chip("VIP", tone="pink", icon="diamond"))
        self.assertIn("VIP", html)
        self.assertIn("diamond", html)
        self.assertIn("jh-chip", html)

    def test_chips_renders_multiple(self):
        html = str(chips([("A", "success"), ("B", "warning")]))
        self.assertIn("A", html)
        self.assertIn("B", html)
        self.assertIn("jh-chips", html)

    def test_time_ago_handles_none(self):
        self.assertEqual(time_ago(None), "—")

    def test_time_ago_relative(self):
        now = timezone.now()
        self.assertEqual(time_ago(now), "ahora mismo")
        self.assertIn("min", time_ago(now - timedelta(minutes=5)))
        self.assertIn("h", time_ago(now - timedelta(hours=3)))
        self.assertIn("día", time_ago(now - timedelta(days=2)))
        self.assertIn("mes", time_ago(now - timedelta(days=60)))
        self.assertIn("año", time_ago(now - timedelta(days=400)))

    def test_contact_actions_with_phone_email_and_telegram(self):
        u = User(
            username="x", email="x@x.com", phone="+51 987 654 321",
            telegram_username="@xyz",
        )
        html = str(contact_actions(u))
        self.assertIn("wa.me/51987654321", html)
        self.assertIn("mailto:x@x.com", html)
        self.assertIn("t.me/xyz", html)

    def test_contact_actions_with_no_data(self):
        u = User(username="x", email="", phone="", telegram_username="")
        html = str(contact_actions(u))
        self.assertIn("—", html)

    def test_stat_grid_renders_cards(self):
        html = str(stat_grid([
            {"label": "Pedidos", "value": "42", "tone": "cyan", "icon": "receipt_long"},
            {"label": "Total", "value": "S/ 100"},
        ]))
        self.assertIn("Pedidos", html)
        self.assertIn("42", html)
        self.assertIn("Total", html)
        self.assertIn("jh-stat-grid", html)

    def test_modern_table_with_rows(self):
        html = str(modern_table(
            ["#", "Estado"],
            [["123", "Pagado"], ["124", "Entregado"]],
        ))
        self.assertIn("123", html)
        self.assertIn("124", html)
        self.assertIn("jh-table", html)

    def test_modern_table_empty(self):
        html = str(modern_table(["A", "B"], []))
        self.assertIn("Sin registros", html)


class CustomerAdminListColumnsTests(TestCase):
    """Verifica que el changelist de Clientes renderiza el rediseño."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser(
            username="admin2", email="a2@example.com", password="password",
        )
        cls.vip = User.objects.create_user(
            username="vipclient", email="vip@x.com", password="x",
            first_name="Cliente", last_name="VIP", role=Role.CLIENTE,
            phone="+51999888777",
        )
        for _ in range(6):
            Order.objects.create(
                user=cls.vip, email=cls.vip.email,
                total=Decimal("50"), status=Order.Status.DELIVERED,
            )
        cls.nuevo = User.objects.create_user(
            username="nuevo", email="nuevo@x.com", password="x",
            role=Role.CLIENTE,
        )
        Order.objects.create(
            user=cls.nuevo, email=cls.nuevo.email,
            total=Decimal("15"), status=Order.Status.DELIVERED,
        )

    def test_changelist_shows_avatar_chips_and_actions(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin:accounts_customer_changelist"))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("jh-avatar", html)
        self.assertIn("jh-user-cell", html)
        self.assertIn("VIP", html)  # chip de cliente VIP (≥5 pedidos)
        self.assertIn("Nuevo", html)  # chip de cliente nuevo (1 pedido)
        self.assertIn("wa.me/51999888777", html)  # acción WhatsApp


class DistributorAdminListColumnsTests(TestCase):
    """Verifica que el changelist de Distribuidores renderiza el rediseño."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser(
            username="admin3", email="a3@example.com", password="password",
        )
        cls.aprobado = User.objects.create_user(
            username="dist1", email="d1@x.com", password="x",
            role=Role.DISTRIBUIDOR, distributor_approved=True,
            wallet_balance=Decimal("123.45"),
        )
        cls.pendiente = User.objects.create_user(
            username="dist2", email="d2@x.com", password="x",
            role=Role.DISTRIBUIDOR, distributor_approved=False,
        )

    def test_changelist_shows_status_and_wallet_chips(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin:accounts_distributor_changelist"))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("jh-avatar", html)
        self.assertIn("Aprobado", html)
        self.assertIn("Pendiente", html)
        self.assertIn("S/ 123.45", html)


class CustomerChangeFormTests(TestCase):
    """La ficha del cliente debe mostrar el panel de stats y secciones nuevas."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser(
            username="admin4", email="a4@example.com", password="password",
        )
        cls.cli = User.objects.create_user(
            username="ficha", email="ficha@x.com", password="x",
            role=Role.CLIENTE, first_name="Ana", last_name="López",
        )
        Order.objects.create(
            user=cls.cli, email=cls.cli.email,
            total=Decimal("80"), status=Order.Status.DELIVERED,
        )

    def test_change_form_renders_stats_panel(self):
        self.client.force_login(self.staff)
        url = reverse("admin:accounts_customer_change", args=[self.cli.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("jh-stat-grid", html)
        self.assertIn("Pedidos", html)
        self.assertIn("Total gastado", html)
        self.assertIn("Ticket promedio", html)
        self.assertIn("Última compra", html)
