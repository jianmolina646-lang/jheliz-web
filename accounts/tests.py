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
