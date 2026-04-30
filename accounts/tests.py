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
