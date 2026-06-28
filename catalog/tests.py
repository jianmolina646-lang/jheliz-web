from datetime import timedelta
from decimal import Decimal

from django.contrib.admin.sites import site as admin_site
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.admin import StockItemAdmin
from catalog.models import (
    Category,
    Plan,
    Product,
    ProductMode,
    ProductReview,
    PromoBanner,
    StockItem,
)


class StockUrgencyTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="Test", slug="test")
        self.product = Product.objects.create(
            category=self.cat, name="Demo", slug="demo", is_active=True,
        )
        self.plan = Plan.objects.create(
            product=self.product, name="1 mes",
            price_customer=Decimal("10.00"), low_stock_threshold=5,
        )

    def _add_stock(self, n: int):
        for i in range(n):
            StockItem.objects.create(
                product=self.product, plan=self.plan,
                credentials=f"creds-{i}",
            )

    def test_no_stock_no_urgency(self):
        self.assertEqual(self.product.stock_urgency_level, "")
        self.assertFalse(self.product.is_low_stock)

    def test_critical_when_two_or_less(self):
        self._add_stock(2)
        self.assertEqual(self.product.stock_urgency_level, "critical")
        self.assertTrue(self.product.is_low_stock)

    def test_low_when_within_threshold(self):
        self._add_stock(4)
        self.assertEqual(self.product.stock_urgency_level, "low")

    def test_no_urgency_above_threshold(self):
        self._add_stock(10)
        self.assertEqual(self.product.stock_urgency_level, "")
        self.assertFalse(self.product.is_low_stock)


class StockImportDuplicateTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.get_or_create(slug="streaming", defaults={"name": "Streaming"})[0]
        self.product = Product.objects.create(
            category=self.cat,
            name="Netflix Premium — 1 perfil",
            slug="netflix-premium-1-perfil",
            is_active=True,
        )
        self.plan = Plan.objects.create(
            product=self.product,
            name="1 mes",
            price_customer=Decimal("25.00"),
        )
        # Producto de cuenta completa: aquí sí se deduplica (no se debe
        # cargar dos veces la misma cuenta entera).
        self.completa_product = Product.objects.create(
            category=self.cat,
            name="Netflix Cuenta Completa",
            slug="netflix-cuenta-completa",
            mode=ProductMode.COMPLETA,
            is_active=True,
        )
        self.completa_plan = Plan.objects.create(
            product=self.completa_product,
            name="1 mes",
            price_customer=Decimal("60.00"),
        )
        self.admin = StockItemAdmin(StockItem, admin_site)

    def test_allows_repeated_email_for_perfil_product(self):
        # Escenario del usuario: vende perfiles y pega el mismo correo dos
        # veces (mismo correo+clave, sin perfil). Ambas líneas deben crear
        # un StockItem (un perfil cada una).
        created, skipped = self.admin._process_file_with_stats(
            "mamaniengel78@gmail.com|premium2025\n"
            "mamaniengel78@gmail.com|premium2025",
            product=self.product,
            plan=self.plan,
        )

        self.assertEqual(created, 2)
        self.assertEqual(skipped, 0)
        self.assertEqual(self.product.stock_items.count(), 2)

    def test_allows_same_email_when_profile_is_different(self):
        StockItem.objects.create(
            product=self.product,
            plan=self.plan,
            credentials=(
                "Correo: cuenta@netflix.com\n"
                "Contraseña: secret\n"
                "Perfil: Perfil 1\n"
                "PIN: 1111"
            ),
        )

        created, skipped = self.admin._process_file_with_stats(
            "cuenta@netflix.com|otra-clave|Perfil 2|2222",
            product=self.product,
            plan=self.plan,
        )

        self.assertEqual(created, 1)
        self.assertEqual(skipped, 0)
        self.assertEqual(self.product.stock_items.count(), 2)

    def test_rejects_same_email_and_same_profile_for_completa(self):
        StockItem.objects.create(
            product=self.completa_product,
            plan=self.completa_plan,
            credentials=(
                "Correo: cuenta@netflix.com\n"
                "Contraseña: secret\n"
                "Perfil: Perfil 1\n"
                "PIN: 1111"
            ),
        )

        created, skipped = self.admin._process_file_with_stats(
            "cuenta@netflix.com|otra-clave|Perfil 1|9999",
            product=self.completa_product,
            plan=self.completa_plan,
        )

        self.assertEqual(created, 0)
        self.assertEqual(skipped, 1)
        self.assertEqual(self.completa_product.stock_items.count(), 1)

    def test_rejects_generic_account_when_same_email_already_exists_for_completa(self):
        StockItem.objects.create(
            product=self.completa_product,
            plan=self.completa_plan,
            credentials=(
                "Correo: cuenta@netflix.com\n"
                "Contraseña: secret\n"
                "Perfil: Perfil 1\n"
                "PIN: 1111"
            ),
        )

        created, skipped = self.admin._process_file_with_stats(
            "cuenta@netflix.com|otra-clave",
            product=self.completa_product,
            plan=self.completa_plan,
        )

        self.assertEqual(created, 0)
        self.assertEqual(skipped, 1)
        self.assertEqual(self.completa_product.stock_items.count(), 1)


class PromoBannerTests(TestCase):
    def test_inactive_returns_none(self):
        PromoBanner.objects.create(
            name="Off", text="Promo", is_active=False,
        )
        self.assertIsNone(PromoBanner.get_active())

    def test_active_returned(self):
        b = PromoBanner.objects.create(name="On", text="Promo")
        self.assertEqual(PromoBanner.get_active(), b)

    def test_expired_not_returned(self):
        past = timezone.now() - timedelta(days=1)
        PromoBanner.objects.create(
            name="Old", text="Old", ends_at=past,
        )
        self.assertIsNone(PromoBanner.get_active())

    def test_future_not_returned(self):
        future = timezone.now() + timedelta(days=1)
        PromoBanner.objects.create(
            name="Future", text="Soon", starts_at=future,
        )
        self.assertIsNone(PromoBanner.get_active())

    def test_home_only_filtering(self):
        PromoBanner.objects.create(
            name="HomeOnly", text="Home", show_only_on_home=True,
        )
        self.assertIsNone(PromoBanner.get_active(on_home=False))
        self.assertIsNotNone(PromoBanner.get_active(on_home=True))


class ProductReviewTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="Test", slug="testreview")
        self.product = Product.objects.create(
            category=self.cat, name="Demo", slug="demo-review", is_active=True,
        )
        Plan.objects.create(
            product=self.product, name="1 mes",
            price_customer=Decimal("10.00"),
        )
        self.review = ProductReview.objects.create(
            product=self.product,
            author_name="Cliente",
            email="x@y.com",
            rating=5,
            comment="",
            status=ProductReview.Status.PENDING,
            is_verified=True,
        )

    def test_token_generated(self):
        self.assertTrue(self.review.token)
        self.assertEqual(len(self.review.token), 32)

    def test_submit_review_form(self):
        client = Client()
        url = reverse("catalog:review_submit", args=[self.review.token])
        resp = client.post(url, {
            "author_name": "Carla M.",
            "city": "Lima",
            "rating": "5",
            "title": "Top",
            "comment": "Llegó super rápido y todo bien.",
        })
        self.assertRedirects(resp, reverse("catalog:review_thanks"))
        self.review.refresh_from_db()
        self.assertEqual(self.review.author_name, "Carla M.")
        self.assertEqual(self.review.rating, 5)
        self.assertTrue(self.review.is_verified)

    def test_submit_review_short_comment_fails(self):
        client = Client()
        url = reverse("catalog:review_submit", args=[self.review.token])
        resp = client.post(url, {
            "author_name": "X",
            "rating": "5",
            "comment": "corto",
        })
        self.assertEqual(resp.status_code, 200)
        self.review.refresh_from_db()
        self.assertNotEqual(self.review.author_name, "X")

    def test_thanks_page(self):
        resp = Client().get(reverse("catalog:review_thanks"))
        self.assertEqual(resp.status_code, 200)

    def test_approved_review_visible_on_product_page(self):
        self.review.author_name = "Carla"
        self.review.comment = "Top, llegó al toque y funciona perfecto."
        self.review.status = ProductReview.Status.APPROVED
        self.review.save()
        resp = Client().get(self.product.get_absolute_url())
        self.assertContains(resp, "Carla")
        self.assertContains(resp, "Compra verificada")

    def test_pending_review_hidden_on_product_page(self):
        resp = Client().get(self.product.get_absolute_url())
        self.assertNotContains(resp, "Top, llegó al toque")


class StockModuleViewsTests(TestCase):
    """Verifica el rediseño del módulo de stock: overview, list HTMX, header común."""

    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="stockstaff", email="ss@example.com", password="pwd1234!", is_staff=True,
        )
        self.user = User.objects.create_user(
            username="cliente", email="c@example.com", password="pwd1234!",
        )
        self.cat = Category.objects.create(name="Streaming-mod", slug="streaming-mod")
        self.product_a = Product.objects.create(
            category=self.cat, name="Netflix Demo", slug="netflix-demo", is_active=True,
        )
        self.product_b = Product.objects.create(
            category=self.cat, name="Disney Demo", slug="disney-demo", is_active=True,
        )
        Plan.objects.create(
            product=self.product_a, name="1 mes",
            price_customer=Decimal("10.00"), low_stock_threshold=3,
        )
        StockItem.objects.create(
            product=self.product_a, credentials="alice@x.com|pw1", label="Perfil 1",
        )
        StockItem.objects.create(
            product=self.product_a, credentials="alice@x.com|pw1", label="Perfil 2",
            status=StockItem.Status.SOLD,
        )
        StockItem.objects.create(
            product=self.product_b, credentials="bob@x.com|pw2",
        )

    def test_overview_requires_staff(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("admin_stock_overview"))
        self.assertNotEqual(resp.status_code, 200)

    def test_overview_renders_kpis_and_tabs(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_stock_overview"))
        self.assertEqual(resp.status_code, 200)
        # KPIs visibles en el header
        self.assertContains(resp, "Disponibles")
        # Cards de productos
        self.assertContains(resp, "Netflix Demo")
        self.assertContains(resp, "Disney Demo")
        # Tabs visibles (link al list view)
        self.assertContains(resp, reverse("admin_stock_list"))
        # Resumen tab activo (clase distintiva primary-500)
        self.assertContains(resp, "bg-primary-500")

    def test_overview_search_filters_cards(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_stock_overview") + "?q=netflix")
        self.assertContains(resp, "Netflix Demo")
        self.assertNotContains(resp, "Disney Demo")

    def test_list_requires_staff(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("admin_stock_list"))
        self.assertNotEqual(resp.status_code, 200)

    def test_list_full_page_renders_filters_and_rows(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_stock_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Netflix Demo")
        self.assertContains(resp, "Disney Demo")
        # Filtro de status presente con los 5 estados
        for label in ("Disponibles", "Vendidas", "Reservadas", "Caídas", "Deshabilitadas"):
            self.assertContains(resp, label)
        # Vista del header común (KPIs)
        self.assertContains(resp, "Inventario")

    def test_list_status_filter(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_stock_list") + "?status=sold")
        # Solo la del item vendido (alice@x.com con label Perfil 2) debería aparecer
        # Both rows show "alice@x.com" credentials so check via label
        self.assertContains(resp, "Perfil 2")
        self.assertNotContains(resp, "Perfil 1")

    def test_list_product_filter(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_stock_list") + f"?product={self.product_b.pk}")
        self.assertContains(resp, "Disney Demo")
        # No debe aparecer el item de Netflix
        self.assertNotContains(resp, "Perfil 1")

    def test_list_search_q(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_stock_list") + "?q=alice")
        self.assertContains(resp, "Perfil 1")
        self.assertNotContains(resp, "bob@x.com")

    def test_list_htmx_returns_partial_only(self):
        """Una request HTMX debe devolver solo la tabla, sin el header completo."""
        self.client.force_login(self.staff)
        resp = self.client.get(
            reverse("admin_stock_list"),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        # El partial NO incluye el header común (Inventario / tabs)
        self.assertNotContains(resp, "Inventario")
        # Pero SÍ debe incluir la tabla con resultados
        self.assertContains(resp, "Netflix Demo")
        # Y el wrapper usado para hx-target / hx-select
        self.assertContains(resp, 'id="stock-list-results"')

    def test_import_view_uses_unified_header(self):
        """La vista de import también muestra el header común con tabs."""
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin:catalog_stockitem_import"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Inventario")  # header
        self.assertContains(resp, reverse("admin_stock_overview"))


class CheapestVisiblePlanTests(TestCase):
    """El `DESDE` de la card debe ignorar planes en S/ 0 o sólo-distribuidor."""

    def setUp(self):
        self.cat = Category.objects.create(name="Streaming-pp", slug="streaming-pp")
        self.product = Product.objects.create(
            category=self.cat, name="Prime Video Demo", slug="prime-video-demo",
            is_active=True,
        )

    def test_skips_zero_price_plan(self):
        Plan.objects.create(
            product=self.product, name="Borrador", duration_days=15,
            price_customer=Decimal("0.00"), order=0,
        )
        Plan.objects.create(
            product=self.product, name="1 mes", duration_days=30,
            price_customer=Decimal("8.00"), order=1,
        )
        plan = self.product.cheapest_visible_plan(None)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.price_customer, Decimal("8.00"))

    def test_picks_minimum_nonzero_price(self):
        Plan.objects.create(
            product=self.product, name="3 meses", duration_days=90,
            price_customer=Decimal("20.00"), order=0,
        )
        Plan.objects.create(
            product=self.product, name="1 mes", duration_days=30,
            price_customer=Decimal("8.00"), order=1,
        )
        plan = self.product.cheapest_visible_plan(None)
        self.assertEqual(plan.price_customer, Decimal("8.00"))

    def test_skips_distributor_only_plan_for_anon_user(self):
        Plan.objects.create(
            product=self.product, name="Mayorista", duration_days=30,
            price_customer=Decimal("3.00"), available_for_customer=False, order=0,
        )
        Plan.objects.create(
            product=self.product, name="1 mes", duration_days=30,
            price_customer=Decimal("8.00"), order=1,
        )
        plan = self.product.cheapest_visible_plan(None)
        self.assertEqual(plan.price_customer, Decimal("8.00"))

    def test_returns_none_when_only_zero_priced_plans(self):
        Plan.objects.create(
            product=self.product, name="Borrador", duration_days=30,
            price_customer=Decimal("0.00"), order=0,
        )
        self.assertIsNone(self.product.cheapest_visible_plan(None))

    def test_card_shows_nonzero_price_when_zero_plan_exists(self):
        """Regresión: la card pública no debe mostrar `S/ 0,00` como `DESDE`."""
        Plan.objects.create(
            product=self.product, name="Borrador", duration_days=15,
            price_customer=Decimal("0.00"), order=0,
        )
        Plan.objects.create(
            product=self.product, name="1 mes", duration_days=30,
            price_customer=Decimal("8.00"), order=1,
        )
        resp = self.client.get(reverse("catalog:products"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Prime Video Demo")
        self.assertContains(resp, "$ 8,00")
        self.assertNotContains(resp, "$ 0,00")


class DistributorPanelTests(TestCase):
    """Cubre el dashboard nuevo, edición de cliente final y reporte de cuenta caída."""

    def setUp(self):
        from orders.models import Order, OrderItem
        User = get_user_model()
        self.client = Client()
        self.distri = User.objects.create_user(
            username="distri1",
            password="ClaveDistri.123!",
            email="d1@example.com",
            role="distribuidor",
            distributor_approved=True,
        )
        self.cliente = User.objects.create_user(
            username="cli1",
            password="ClaveCliente.123!",
            email="c1@example.com",
            role="cliente",
        )
        self.cat = Category.objects.get_or_create(slug="streaming", defaults={"name": "Streaming"})[0]
        self.prod = Product.objects.create(
            category=self.cat, name="Netflix", slug="netflix", is_active=True,
        )
        self.plan = Plan.objects.create(
            product=self.prod, name="1 mes", duration_days=30,
            price_customer=Decimal("20.00"), price_distributor=Decimal("12.00"),
            available_for_distributor=True, order=1,
        )
        self.order = Order.objects.create(
            user=self.distri,
            email="d1@example.com",
            total=Decimal("12.00"),
        )
        self.item = OrderItem.objects.create(
            order=self.order,
            product=self.prod, plan=self.plan,
            product_name=self.prod.name, plan_name=self.plan.name,
            unit_price=Decimal("12.00"), quantity=1,
            delivered_credentials="correo: x@y.com\nclave: 1234",
            expires_at=timezone.now() + timedelta(days=3),
        )

    def test_panel_requires_login(self):
        resp = self.client.get(reverse("catalog:distributor_panel"))
        self.assertEqual(resp.status_code, 302)

    def test_panel_redirects_for_non_distributor(self):
        self.client.force_login(self.cliente)
        resp = self.client.get(reverse("catalog:distributor_panel"))
        self.assertRedirects(resp, reverse("catalog:distributor"))

    def test_panel_renders_for_approved_distributor(self):
        self.client.force_login(self.distri)
        resp = self.client.get(reverse("catalog:distributor_panel"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Panel distribuidor")
        # Métricas presentes
        self.assertContains(resp, "Gasto este mes")
        self.assertContains(resp, "Ahorraste este mes")
        # Item del distribuidor aparece en el libro
        self.assertContains(resp, "Netflix")
        # Ahorro mensual = (20 - 12) * 1 = 8.00 → debe aparecer formateado
        self.assertContains(resp, "8,00")

    def test_edit_customer_saves_data(self):
        self.client.force_login(self.distri)
        resp = self.client.post(
            reverse("catalog:distributor_edit_customer", args=[self.item.pk]),
            {
                "final_customer_name": "Juan Cliente",
                "final_customer_whatsapp": "51999111222",
                "final_customer_notes": "VIP",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.final_customer_name, "Juan Cliente")
        # Normaliza prefijo +
        self.assertEqual(self.item.final_customer_whatsapp, "+51999111222")
        self.assertEqual(self.item.final_customer_notes, "VIP")

    def test_edit_customer_only_for_owner(self):
        from orders.models import Order, OrderItem
        User = get_user_model()
        otro = User.objects.create_user(
            username="distri2", password="ClaveDistri.456!",
            role="distribuidor", distributor_approved=True,
        )
        otro_order = Order.objects.create(user=otro, email="x@x.com", total=Decimal("12.00"))
        otro_item = OrderItem.objects.create(
            order=otro_order, product=self.prod, plan=self.plan,
            product_name=self.prod.name, plan_name=self.plan.name,
            unit_price=Decimal("12.00"), quantity=1,
        )
        self.client.force_login(self.distri)
        resp = self.client.post(
            reverse("catalog:distributor_edit_customer", args=[otro_item.pk]),
            {"final_customer_name": "intento"},
        )
        # 404 por el filtro order__user=request.user
        self.assertEqual(resp.status_code, 404)

    def test_report_broken_marks_item_and_notifies(self):
        from unittest.mock import patch
        self.client.force_login(self.distri)
        with patch("orders.telegram.notify_admin") as mock_notify:
            resp = self.client.post(
                reverse("catalog:distributor_report_broken", args=[self.item.pk]),
                {"note": "no carga la app"},
            )
        self.assertEqual(resp.status_code, 302)
        self.item.refresh_from_db()
        self.assertIsNotNone(self.item.reported_broken_at)
        self.assertEqual(self.item.reported_broken_note, "no carga la app")
        mock_notify.assert_called_once()

    def test_catalog_view_renders_for_distributor(self):
        self.client.force_login(self.distri)
        resp = self.client.get(reverse("catalog:distributor_catalog"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Catálogo")


class BackInStockAlertTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="Streaming-bis", slug="streaming-bis")
        self.product = Product.objects.create(
            category=self.cat,
            name="Test BIS Product",
            slug="test-bis-product",
            is_active=True,
        )
        self.plan = Plan.objects.create(
            product=self.product, name="1 mes",
            price_customer=Decimal("25.00"),
        )
        self.client = Client()

    def test_subscribe_creates_alert(self):
        from catalog.models import BackInStockAlert

        url = reverse(
            "catalog:back_in_stock_subscribe",
            kwargs={"slug": self.product.slug},
        )
        resp = self.client.post(url, {"email": "user@test.com"}, follow=True)
        self.assertEqual(resp.status_code, 200)
        alert = BackInStockAlert.objects.get(
            email="user@test.com", product=self.product,
        )
        self.assertEqual(alert.status, BackInStockAlert.Status.PENDING)

    def test_subscribe_duplicate_does_not_create_second(self):
        from catalog.models import BackInStockAlert

        url = reverse(
            "catalog:back_in_stock_subscribe",
            kwargs={"slug": self.product.slug},
        )
        self.client.post(url, {"email": "user@test.com"})
        self.client.post(url, {"email": "user@test.com"})
        count = BackInStockAlert.objects.filter(
            email="user@test.com", product=self.product,
        ).count()
        self.assertEqual(count, 1)

    def test_subscribe_invalid_email_rejected(self):
        from catalog.models import BackInStockAlert

        url = reverse(
            "catalog:back_in_stock_subscribe",
            kwargs={"slug": self.product.slug},
        )
        resp = self.client.post(url, {"email": "not-an-email"}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(
            BackInStockAlert.objects.filter(product=self.product).exists()
        )

    def test_signal_notifies_when_new_stock_available(self):
        from django.core import mail
        from catalog.models import BackInStockAlert

        BackInStockAlert.objects.create(
            email="alert1@test.com",
            product=self.product, plan=self.plan,
            status=BackInStockAlert.Status.PENDING,
        )
        BackInStockAlert.objects.create(
            email="alert2@test.com",
            product=self.product, plan=None,
            status=BackInStockAlert.Status.PENDING,
        )
        # Crear un StockItem AVAILABLE → dispara el signal.
        StockItem.objects.create(
            product=self.product, plan=self.plan,
            credentials="email: foo\nclave: bar",
            status=StockItem.Status.AVAILABLE,
        )
        # Ambas alertas deberían quedar como NOTIFIED.
        notified = BackInStockAlert.objects.filter(
            status=BackInStockAlert.Status.NOTIFIED,
        ).count()
        self.assertEqual(notified, 2)
        # Y deberían haberse mandado 2 correos.
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(
            any("Volvi" in m.subject for m in mail.outbox),
            f"Subjects: {[m.subject for m in mail.outbox]}",
        )

    def test_signal_does_not_re_notify_already_notified(self):
        from catalog.models import BackInStockAlert

        BackInStockAlert.objects.create(
            email="already@test.com",
            product=self.product, plan=self.plan,
            status=BackInStockAlert.Status.NOTIFIED,
            notified_at=timezone.now(),
        )
        StockItem.objects.create(
            product=self.product, plan=self.plan,
            credentials="email: foo\nclave: bar",
        )
        # Ya estaba notified, no se vuelve a tocar.
        alert = BackInStockAlert.objects.get(email="already@test.com")
        self.assertEqual(alert.status, BackInStockAlert.Status.NOTIFIED)


class RecentPurchasesApiTests(TestCase):
    """El endpoint /api/compras-recientes/ devuelve los últimos pedidos
    pagados/entregados con ciudad y emoji. Se usa para el widget de toasts
    de prueba social en el frontend."""

    def setUp(self):
        from orders.models import Order, OrderItem
        from django.core.cache import cache
        cache.clear()
        self.User = get_user_model()
        self.cat = Category.objects.create(
            name="StreamingRecent", slug="streaming-recent", emoji="📺",
        )
        self.product = Product.objects.create(
            category=self.cat, name="Netflix Premium", slug="netflix-recent", is_active=True,
        )
        self.plan = Plan.objects.create(
            product=self.product, name="1 mes", price_customer=Decimal("25.00"),
        )
        self.user = self.User.objects.create_user(
            username="seba", email="seba@test.pe", first_name="Sebastián",
        )
        self.order = Order.objects.create(
            user=self.user, total=Decimal("25.00"), status=Order.Status.PAID,
        )
        OrderItem.objects.create(
            order=self.order, product=self.product, plan=self.plan, quantity=1,
            product_name=self.product.name, plan_name=self.plan.name,
            unit_price=Decimal("25.00"),
        )

    def test_returns_json_with_paid_order(self):
        resp = self.client.get(reverse("catalog:recent_purchases_api"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("items", data)
        self.assertGreaterEqual(len(data["items"]), 1)
        item = data["items"][0]
        self.assertEqual(item["name"], "Sebastián")
        self.assertEqual(item["product"], "Netflix Premium")
        self.assertEqual(item["emoji"], "📺")
        self.assertTrue(item["city"])  # ciudad peruana asignada por id
        self.assertIn("when_iso", item)

    def test_excludes_unpaid_orders(self):
        from orders.models import Order, OrderItem
        order = Order.objects.create(
            user=self.user, total=Decimal("25.00"), status=Order.Status.PENDING,
        )
        OrderItem.objects.create(
            order=order, product=self.product, plan=self.plan, quantity=1,
            product_name=self.product.name, plan_name=self.plan.name,
            unit_price=Decimal("25.00"),
        )
        from django.core.cache import cache
        cache.clear()
        resp = self.client.get(reverse("catalog:recent_purchases_api"))
        data = resp.json()
        # Solo el pedido pagado (1 item), no el pending.
        self.assertEqual(len(data["items"]), 1)


class ProductFaqTests(TestCase):
    """La página de detalle de producto debe mostrar el bloque de FAQs
    dinámicas + emitir el FAQPage JSON-LD para SEO."""

    def setUp(self):
        self.cat = Category.objects.create(
            name="Streaming-FAQ", slug="streaming-faq", emoji="📺",
        )
        self.product = Product.objects.create(
            category=self.cat, name="Netflix FAQ", slug="netflix-faq",
            is_active=True, mode="perfil", delivery_is_instant=True,
        )
        self.plan = Plan.objects.create(
            product=self.product, name="1 mes",
            price_customer=Decimal("25.00"),
        )

    def test_faq_section_renders_on_product_detail(self):
        resp = self.client.get(
            reverse("catalog:product", kwargs={"slug": self.product.slug})
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        # La sección destacada
        self.assertIn("Preguntas frecuentes", body)
        self.assertIn("¿Tenés dudas sobre Netflix FAQ?", body)
        # Pregunta base de entrega
        self.assertIn("¿Cuánto demora la entrega de Netflix FAQ?", body)
        # Pregunta del modo perfil
        self.assertIn("¿Netflix FAQ funciona en mi Smart TV?", body)

    def test_faq_jsonld_is_emitted_for_seo(self):
        resp = self.client.get(
            reverse("catalog:product", kwargs={"slug": self.product.slug})
        )
        body = resp.content.decode()
        self.assertIn('"@type": "FAQPage"', body)
        self.assertIn('"@type": "Question"', body)

    def test_faq_for_licencia_product(self):
        """Un producto en modo licencia muestra preguntas distintas."""
        prod = Product.objects.create(
            category=self.cat, name="Office 365", slug="office-365-faq",
            is_active=True, mode="licencia",
        )
        Plan.objects.create(product=prod, name="1 año", price_customer=Decimal("50.00"))
        resp = self.client.get(
            reverse("catalog:product", kwargs={"slug": prod.slug})
        )
        body = resp.content.decode()
        self.assertIn("¿Cómo activo Office 365?", body)
        self.assertIn("¿La licencia es legal y permanente?", body)


class ProductDetailRendersOutsideContentBlockTests(TestCase):
    """Regression: el JS de tabs y la sección de productos relacionados
    deben estar dentro de {% block content %} para que se rendericen."""

    def setUp(self):
        self.cat = Category.objects.create(
            name="Streaming-Tabs", slug="streaming-tabs", emoji="📺",
        )
        self.product = Product.objects.create(
            category=self.cat, name="Netflix Tabs", slug="netflix-tabs",
            is_active=True, mode="perfil",
        )
        Plan.objects.create(
            product=self.product, name="1 mes",
            price_customer=Decimal("25.00"),
        )

    def test_tabs_js_is_rendered(self):
        resp = self.client.get(
            reverse("catalog:product", kwargs={"slug": self.product.slug})
        )
        body = resp.content.decode()
        # El JS que activa los tabs debe estar en la página, si no los tabs
        # "Garantía y soporte" y "Preguntas frecuentes" no abren su panel.
        self.assertIn("querySelector('[data-pd-tabs]')", body)
        # Los 3 tabs y sus paneles deben estar presentes.
        self.assertIn('data-pd-tab="desc"', body)
        self.assertIn('data-pd-tab="garantia"', body)
        self.assertIn('data-pd-tab="faq"', body)
        self.assertIn('data-pd-panel="garantia"', body)
        self.assertIn('data-pd-panel="faq"', body)


class AdminPWAEndpointsTests(TestCase):
    """Verifica que el panel admin tiene su propio manifest + service worker
    para poder instalarse como PWA."""

    def test_admin_manifest_returns_json(self):
        resp = self.client.get("/panel-virtualidadsp/manifest.webmanifest")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/json", resp["Content-Type"])
        import json as _json
        data = _json.loads(resp.content)
        self.assertEqual(data["short_name"], "VirtualidadSP Admin")
        self.assertEqual(data["scope"], "/panel-virtualidadsp/")
        self.assertEqual(data["display"], "standalone")
        # Debe declarar al menos 1 icono.
        self.assertGreaterEqual(len(data["icons"]), 1)

    def test_admin_service_worker_is_javascript(self):
        resp = self.client.get("/panel-virtualidadsp/sw.js")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("javascript", resp["Content-Type"])
        # Scope dedicado al admin.
        self.assertEqual(resp["Service-Worker-Allowed"], "/panel-virtualidadsp/")
        # Network-only para no servir datos viejos del admin.
        body = resp.content.decode()
        self.assertIn("self.addEventListener('install'", body)
        self.assertIn("self.addEventListener('fetch'", body)

    def test_admin_password_reset_url_exists(self):
        # El template templates/admin/login.html referencia este url-name;
        # antes no estaba registrado y el "¿Olvidaste tu contraseña?" del
        # login quedaba como link muerto.
        from django.urls import reverse
        url = reverse("admin_password_reset")
        self.assertEqual(url, "/panel-virtualidadsp/password_reset/")
        resp = self.client.get(url)
        # Misma view que el reset público (200 con el formulario).
        self.assertEqual(resp.status_code, 200)


class DistributorPortalNewPagesTests(TestCase):
    """Pruebas de las 3 páginas nuevas del portal del distribuidor:
    cuentas, calendario y soporte."""

    def setUp(self):
        from orders.models import Order, OrderItem
        User = get_user_model()
        self.client = Client()
        self.distri = User.objects.create_user(
            username="distri_portal",
            password="ClavePortal.123!",
            email="portal@example.com",
            role="distribuidor",
            distributor_approved=True,
        )
        self.cliente = User.objects.create_user(
            username="cli_portal",
            password="ClaveCliente.123!",
            email="cli_portal@example.com",
            role="cliente",
        )
        self.cat = Category.objects.get_or_create(slug="streaming", defaults={"name": "Streaming"})[0]
        self.prod = Product.objects.create(
            category=self.cat, name="Netflix", slug="netflix", is_active=True,
        )
        self.plan = Plan.objects.create(
            product=self.prod, name="1 mes", duration_days=30,
            price_customer=Decimal("20.00"), price_distributor=Decimal("12.00"),
            available_for_distributor=True, order=1,
        )
        from orders.models import Order as _Order
        self.order = Order.objects.create(
            user=self.distri,
            email="portal@example.com",
            total=Decimal("12.00"),
            status=_Order.Status.DELIVERED,
        )
        self.item = OrderItem.objects.create(
            order=self.order,
            product=self.prod, plan=self.plan,
            product_name=self.prod.name, plan_name=self.plan.name,
            unit_price=Decimal("12.00"), quantity=1,
            delivered_credentials="correo: x@y.com\nclave: 1234",
            expires_at=timezone.now() + timedelta(days=3),
        )

    # ---------------------- cuentas ----------------------
    def test_accounts_requires_login(self):
        resp = self.client.get(reverse("catalog:distributor_accounts"))
        self.assertEqual(resp.status_code, 302)

    def test_accounts_redirects_for_non_distributor(self):
        self.client.force_login(self.cliente)
        resp = self.client.get(reverse("catalog:distributor_accounts"))
        self.assertRedirects(resp, reverse("catalog:distributor"))

    def test_accounts_renders_for_distributor(self):
        self.client.force_login(self.distri)
        resp = self.client.get(reverse("catalog:distributor_accounts"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Netflix")
        # Credenciales parseadas mostradas
        self.assertContains(resp, "x@y.com")

    def test_accounts_search_filter(self):
        self.client.force_login(self.distri)
        resp = self.client.get(reverse("catalog:distributor_accounts") + "?q=Netflix")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Netflix")

    # ---------------------- calendar ---------------------
    def test_calendar_requires_login(self):
        resp = self.client.get(reverse("catalog:distributor_calendar"))
        self.assertEqual(resp.status_code, 302)

    def test_calendar_renders_for_distributor(self):
        self.client.force_login(self.distri)
        resp = self.client.get(reverse("catalog:distributor_calendar"))
        self.assertEqual(resp.status_code, 200)

    def test_calendar_handles_custom_month(self):
        self.client.force_login(self.distri)
        resp = self.client.get(reverse("catalog:distributor_calendar") + "?month=2026-12")
        self.assertEqual(resp.status_code, 200)

    def test_calendar_ignores_invalid_month_param(self):
        # No debe romper con basura en ?month
        self.client.force_login(self.distri)
        resp = self.client.get(reverse("catalog:distributor_calendar") + "?month=invalid")
        self.assertEqual(resp.status_code, 200)

    # ---------------------- support ----------------------
    def test_support_requires_login(self):
        resp = self.client.get(reverse("catalog:distributor_support"))
        self.assertEqual(resp.status_code, 302)

    def test_support_renders_for_distributor(self):
        self.client.force_login(self.distri)
        resp = self.client.get(reverse("catalog:distributor_support"))
        self.assertEqual(resp.status_code, 200)
        # 3 motivos rápidos
        self.assertContains(resp, "Suscripción caída")
        self.assertContains(resp, "Error de contraseña")


class SupportTipoPresetTests(TestCase):
    """El formulario de ticket público acepta ?tipo=caida|password|codigo
    para mostrar un hint contextual y prellenar el asunto. Usado por los
    botones del distributor_support."""

    def setUp(self):
        User = get_user_model()
        self.client = Client()
        self.user = User.objects.create_user(
            username="tipopreset", password="Clave.123!", email="t@p.com",
        )

    def test_no_tipo_no_hint(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("support:create"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Ayudanos a resolver rápido")

    def test_tipo_caida_shows_hint_and_prefills_subject(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("support:create") + "?tipo=caida")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Ayudanos a resolver rápido")
        # Asunto pre-llenado
        self.assertContains(resp, "Suscripción caída")

    def test_tipo_password_shows_hint(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("support:create") + "?tipo=password")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Error de contraseña")

    def test_invalid_tipo_no_hint(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("support:create") + "?tipo=invalid")
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Ayudanos a resolver rápido")


class BulkReplaceCredentialsTests(TestCase):
    """Verifica el reemplazo masivo de credenciales en Control de cuentas."""

    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="bulkstaff",
            email="bulk@example.com",
            password="pwd1234!",
            is_staff=True,
        )
        self.cat = Category.objects.create(name="Streaming-bulk", slug="streaming-bulk")
        self.product = Product.objects.create(
            category=self.cat, name="Netflix Bulk", slug="netflix-bulk", is_active=True,
        )
        # 3 cuentas con credenciales bien formadas
        self.it_a = StockItem.objects.create(
            product=self.product,
            credentials="Correo: aa@gmail.com\nContraseña: passA\nPerfil: 1\nPIN: 1111",
        )
        self.it_b = StockItem.objects.create(
            product=self.product,
            credentials="Correo: bb@gmail.com\nContraseña: passB\nPerfil: 2\nPIN: 2222",
        )
        self.it_c = StockItem.objects.create(
            product=self.product,
            credentials="Correo: cc@gmail.com\nContraseña: passC",
        )

    def test_parser_handles_all_formats(self):
        from config.admin_views import _parse_bulk_replace_line

        cases = [
            ("x@gmail.com:newpass", ("x@gmail.com", "", "newpass")),
            ("OLD@gmail.com|new@gmail.com|p1", ("old@gmail.com", "new@gmail.com", "p1")),
            ("old@gmail.com,new@gmail.com,p2", ("old@gmail.com", "new@gmail.com", "p2")),
            ("old@gmail.com -> new@gmail.com:p3", ("old@gmail.com", "new@gmail.com", "p3")),
            ("# comentario", None),
            ("", None),
            ("solo_texto_sin_email", None),
            ("noemail:pass", None),
        ]
        for raw, expected in cases:
            self.assertEqual(_parse_bulk_replace_line(raw), expected, msg=f"input={raw!r}")

    def test_password_only_update(self):
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("admin_stock_bulk_replace_credentials"),
            {"pasted": "aa@gmail.com:nuevaPassA"},
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.it_a.refresh_from_db()
        self.assertIn("nuevaPassA", self.it_a.credentials)
        self.assertIn("aa@gmail.com", self.it_a.credentials)
        # Perfil y PIN se mantienen
        self.assertIn("Perfil: 1", self.it_a.credentials)
        self.assertIn("PIN: 1111", self.it_a.credentials)
        # Las otras no se tocan
        self.it_b.refresh_from_db()
        self.assertIn("passB", self.it_b.credentials)

    def test_email_and_password_update(self):
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("admin_stock_bulk_replace_credentials"),
            {"pasted": "bb@gmail.com|bbnew@gmail.com|nuevaPassB"},
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.it_b.refresh_from_db()
        self.assertIn("bbnew@gmail.com", self.it_b.credentials)
        self.assertNotIn("bb@gmail.com\n", self.it_b.credentials)  # no debería quedar el viejo
        self.assertIn("nuevaPassB", self.it_b.credentials)
        # Perfil/PIN preservados
        self.assertIn("Perfil: 2", self.it_b.credentials)
        self.assertIn("PIN: 2222", self.it_b.credentials)

    def test_email_not_found_reported(self):
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("admin_stock_bulk_replace_credentials"),
            {"pasted": "fantasma@gmail.com:nope"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        msgs = [str(m) for m in resp.context["messages"]]
        self.assertTrue(any("fantasma@gmail.com" in m for m in msgs))

    def test_requires_staff(self):
        # Usuario no-staff debe ser bloqueado
        User = get_user_model()
        u = User.objects.create_user(
            username="nopuede", email="np@example.com", password="x"
        )
        self.client.force_login(u)
        resp = self.client.post(
            reverse("admin_stock_bulk_replace_credentials"),
            {"pasted": "aa@gmail.com:newp"},
        )
        self.assertNotEqual(resp.status_code, 200)
        # No debería haber cambiado nada
        self.it_a.refresh_from_db()
        self.assertIn("passA", self.it_a.credentials)


class CuentasEditBuyerTests(TestCase):
    """Editar nombre del cliente / fecha de una cuenta desde Control de cuentas.

    Cubre el bug que tenía el admin: para corregir el nombre del cliente o
    la fecha de una cuenta vendida, había que entrar a varias pantallas del
    admin clásico. Ahora se puede hacer con un solo botón en la lista.
    """

    def setUp(self):
        from orders.models import Order, OrderItem

        User = get_user_model()
        self.staff = User.objects.create_user(
            username="ebstaff",
            email="eb@example.com",
            password="pwd1234!",
            is_staff=True,
        )
        self.cat = Category.objects.create(name="Streaming-eb", slug="streaming-eb")
        self.product = Product.objects.create(
            category=self.cat, name="Netflix EB", slug="netflix-eb", is_active=True,
        )
        self.plan = Plan.objects.create(
            product=self.product, name="1 mes",
            duration_days=30, price_customer=Decimal("20.00"),
            is_active=True,
        )
        self.item = StockItem.objects.create(
            product=self.product, plan=self.plan,
            credentials="Correo: x@y.com\nContraseña: secret",
            status=StockItem.Status.SOLD,
        )
        self.order = Order.objects.create(
            email="comprador@gmail.com",
            phone="51999111222",
            total=Decimal("20.00"),
            status=Order.Status.DELIVERED,
            paid_at=timezone.now() - timedelta(days=2),
        )
        self.oi = OrderItem.objects.create(
            order=self.order,
            product=self.product, plan=self.plan,
            product_name=self.product.name, plan_name=self.plan.name,
            unit_price=Decimal("20.00"), quantity=1,
            stock_item=self.item,
        )

    def test_edits_customer_name_and_date(self):
        """El POST principal actualiza nombre del cliente final + fecha del pedido."""
        from orders.models import OrderItem

        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("admin_cuentas_edit_buyer", args=[self.item.pk]),
            {
                "customer_name": "María Pérez",
                "customer_whatsapp": "+51 987 654 321",
                "sale_date": "2025-12-31T14:30",
            },
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        oi = OrderItem.objects.get(pk=self.oi.pk)
        self.assertEqual(oi.final_customer_name, "María Pérez")
        self.assertEqual(oi.final_customer_whatsapp, "+51 987 654 321")
        self.order.refresh_from_db()
        # paid_at se guarda en UTC; convertimos a la TZ del proyecto para
        # comparar contra lo que mandó el admin (que estaba en hora local).
        local_dt = timezone.localtime(self.order.paid_at)
        self.assertEqual(local_dt.year, 2025)
        self.assertEqual(local_dt.month, 12)
        self.assertEqual(local_dt.day, 31)
        self.assertEqual(local_dt.hour, 14)
        self.assertEqual(local_dt.minute, 30)

    def test_redirect_returns_to_item_anchor(self):
        """Tras guardar volvemos a la misma cuenta (#cc-item-<pk>), no al tope."""
        self.client.force_login(self.staff)
        # Con ``next`` explícito (caso real del formulario): preserva la URL
        # del dashboard y le agrega el ancla de la cuenta editada.
        resp = self.client.post(
            reverse("admin_cuentas_edit_buyer", args=[self.item.pk]),
            {"customer_name": "Ana", "next": "/panel-virtualidadsp/control-cuentas/?q=x"},
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp["Location"],
            f"/panel-virtualidadsp/control-cuentas/?q=x#cc-item-{self.item.pk}",
        )
        # Sin ``next`` también vuelve a la cuenta sobre el dashboard por defecto.
        resp2 = self.client.post(
            reverse("admin_cuentas_edit_buyer", args=[self.item.pk]),
            {"customer_name": "Ana"},
            follow=False,
        )
        self.assertTrue(resp2["Location"].endswith(f"#cc-item-{self.item.pk}"))

    def test_setting_date_recomputes_expiry_on_existing_item(self):
        """Editar un item sin vencimiento + fecha → se calcula el 'Vence en Xd'."""
        from orders.models import OrderItem

        # El OrderItem del setUp arranca sin expires_at.
        self.assertIsNone(self.oi.expires_at)
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("admin_cuentas_edit_buyer", args=[self.item.pk]),
            {"sale_date": "2026-05-24T10:00"},
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        oi = OrderItem.objects.get(pk=self.oi.pk)
        self.assertIsNotNone(oi.expires_at)
        # Vence = fecha de venta + duración del plan (30 días).
        self.assertEqual((oi.expires_at - oi.order.paid_at).days, self.plan.duration_days)

    def test_backfill_migration_fills_expiry_on_old_sales(self):
        """La migración de backfill calcula el vencimiento de ventas viejas."""
        import importlib

        from django.apps import apps as global_apps
        from orders.models import Order, OrderItem

        _0018 = importlib.import_module(
            "orders.migrations.0018_backfill_orderitem_expires_at",
        )

        # Venta vieja (canal telegram) que quedó sin expires_at, con plan de 30d.
        old_order = Order.objects.create(
            email="viejo@gmail.com",
            total=Decimal("20.00"),
            status=Order.Status.DELIVERED,
            paid_at=timezone.now() - timedelta(days=5),
            channel=Order.Channel.TELEGRAM,
        )
        old_item = StockItem.objects.create(
            product=self.product, plan=self.plan,
            credentials="Correo: viejo@y.com", status=StockItem.Status.SOLD,
        )
        old_oi = OrderItem.objects.create(
            order=old_order, product=self.product, plan=self.plan,
            product_name=self.product.name, plan_name=self.plan.name,
            unit_price=Decimal("20.00"), quantity=1, stock_item=old_item,
        )
        self.assertIsNone(old_oi.expires_at)

        _0018.backfill_expires_at(global_apps, None)

        old_oi.refresh_from_db()
        self.assertIsNotNone(old_oi.expires_at)
        self.assertEqual(
            (old_oi.expires_at - old_order.paid_at).days, self.plan.duration_days,
        )

    def test_edits_buyer_email_normalizes_case(self):
        """El email del comprador se guarda en lowercase."""
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("admin_cuentas_edit_buyer", args=[self.item.pk]),
            {"buyer_email": "NuevoCorreo@Gmail.COM"},
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.email, "nuevocorreo@gmail.com")

    def test_partial_update_only_changes_provided_fields(self):
        """Si solo se manda nombre, el resto no se toca."""
        from orders.models import OrderItem

        original_paid_at = self.order.paid_at
        original_email = self.order.email
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("admin_cuentas_edit_buyer", args=[self.item.pk]),
            {"customer_name": "Solo Nombre"},
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        oi = OrderItem.objects.get(pk=self.oi.pk)
        self.assertEqual(oi.final_customer_name, "Solo Nombre")
        self.order.refresh_from_db()
        self.assertEqual(self.order.paid_at, original_paid_at)
        self.assertEqual(self.order.email, original_email)

    def test_invalid_date_returns_error_message(self):
        """Fechas mal formadas se reportan al usuario sin tocar el pedido."""
        original_paid_at = self.order.paid_at
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("admin_cuentas_edit_buyer", args=[self.item.pk]),
            {"sale_date": "no-es-una-fecha"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        msgs = [str(m) for m in resp.context["messages"]]
        self.assertTrue(any("Fecha inválida" in m for m in msgs), msgs)
        self.order.refresh_from_db()
        self.assertEqual(self.order.paid_at, original_paid_at)

    def test_accepts_date_only_format(self):
        """``2025-12-31`` solo (sin hora) también se acepta."""
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("admin_cuentas_edit_buyer", args=[self.item.pk]),
            {"sale_date": "2025-12-31"},
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        # Convertimos a TZ local para comparar la fecha que mandó el admin.
        local_dt = timezone.localtime(self.order.paid_at)
        self.assertEqual(local_dt.year, 2025)
        self.assertEqual(local_dt.month, 12)
        self.assertEqual(local_dt.day, 31)

    def test_requires_staff(self):
        """Un usuario no-staff no puede editar nada."""
        from orders.models import OrderItem

        User = get_user_model()
        u = User.objects.create_user(
            username="ebnostaff", email="np@example.com", password="x",
        )
        self.client.force_login(u)
        resp = self.client.post(
            reverse("admin_cuentas_edit_buyer", args=[self.item.pk]),
            {"customer_name": "no debería entrar"},
        )
        self.assertNotEqual(resp.status_code, 200)
        oi = OrderItem.objects.get(pk=self.oi.pk)
        self.assertEqual(oi.final_customer_name, "")

    def test_item_without_orderitem_empty_form_shows_hint(self):
        """Cuenta sin pedido + form vacío → info "llená al menos un dato"."""
        from orders.models import OrderItem
        orphan = StockItem.objects.create(
            product=self.product, plan=self.plan,
            credentials="Correo: z@z.com\nContraseña: zzz",
            status=StockItem.Status.AVAILABLE,
        )
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("admin_cuentas_edit_buyer", args=[orphan.pk]),
            {},  # vacío → no se crea nada
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        msgs = [str(m) for m in resp.context["messages"]]
        self.assertTrue(
            any("Lle" in m and "un dato" in m for m in msgs), msgs,
        )
        # No se creó pedido.
        self.assertFalse(OrderItem.objects.filter(stock_item=orphan).exists())
        # Stock sigue disponible.
        orphan.refresh_from_db()
        self.assertEqual(orphan.status, StockItem.Status.AVAILABLE)

    def test_manual_sale_creates_order_and_marks_sold(self):
        """Cuenta Available + datos → crea Order web + OrderItem + marca vendida."""
        from orders.models import Order, OrderItem

        orphan = StockItem.objects.create(
            product=self.product, plan=self.plan,
            credentials="Correo: nuevo@x.com\nContraseña: secret",
            status=StockItem.Status.AVAILABLE,
        )
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("admin_cuentas_edit_buyer", args=[orphan.pk]),
            {
                "customer_name": "Cliente Manual",
                "customer_whatsapp": "+51 911 222 333",
                "buyer_email": "MANUAL@gmail.com",
                "sale_date": "2026-05-24T15:30",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        msgs = [str(m) for m in resp.context["messages"]]
        self.assertTrue(
            any("registrada como venta Web" in m for m in msgs), msgs,
        )

        # Stock vendida + sold_at = fecha que pasamos
        orphan.refresh_from_db()
        self.assertEqual(orphan.status, StockItem.Status.SOLD)
        self.assertIsNotNone(orphan.sold_at)

        # OrderItem creado con final_customer_name correcto
        oi = OrderItem.objects.get(stock_item=orphan)
        self.assertEqual(oi.final_customer_name, "Cliente Manual")
        self.assertEqual(oi.final_customer_whatsapp, "+51 911 222 333")
        self.assertEqual(oi.product_id, self.product.pk)
        self.assertEqual(oi.plan_id, self.plan.pk)
        self.assertEqual(oi.product_name, self.product.name)
        self.assertEqual(oi.plan_name, self.plan.name)
        self.assertEqual(oi.quantity, 1)
        # El vencimiento se calcula igual que en la web: fecha + duración del plan.
        self.assertIsNotNone(oi.expires_at)
        self.assertEqual(
            (oi.expires_at - oi.order.paid_at).days, self.plan.duration_days,
        )

        # Order queda como canal web (se ve igual que una compra normal) + delivered
        order = oi.order
        self.assertEqual(order.channel, Order.Channel.WEB)
        self.assertEqual(order.status, Order.Status.DELIVERED)
        self.assertEqual(order.email, "manual@gmail.com")  # lowercase normalized
        self.assertEqual(order.phone, "+51 911 222 333")
        self.assertIsNotNone(order.paid_at)
        # Fecha respeta lo que pasamos
        from django.utils import timezone as djtz
        local_paid = djtz.localtime(order.paid_at)
        self.assertEqual(local_paid.year, 2026)
        self.assertEqual(local_paid.month, 5)
        self.assertEqual(local_paid.day, 24)
        self.assertEqual(local_paid.hour, 15)
        self.assertEqual(local_paid.minute, 30)

    def test_manual_sale_only_with_date_still_creates_order(self):
        """Solo con la fecha (sin nombre/correo) ya se registra venta manual."""
        from orders.models import OrderItem
        orphan = StockItem.objects.create(
            product=self.product, plan=self.plan,
            credentials="Correo: solo-fecha@x.com\nContraseña: pp",
            status=StockItem.Status.AVAILABLE,
        )
        self.client.force_login(self.staff)
        self.client.post(
            reverse("admin_cuentas_edit_buyer", args=[orphan.pk]),
            {"sale_date": "2026-05-20"},
            follow=True,
        )
        orphan.refresh_from_db()
        self.assertEqual(orphan.status, StockItem.Status.SOLD)
        self.assertTrue(OrderItem.objects.filter(stock_item=orphan).exists())

    def test_manual_sale_invalid_date_does_not_create_order(self):
        """Fecha inválida en venta manual → error, no se crea nada."""
        from orders.models import OrderItem
        orphan = StockItem.objects.create(
            product=self.product, plan=self.plan,
            credentials="Correo: badfecha@x.com\nContraseña: pp",
            status=StockItem.Status.AVAILABLE,
        )
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("admin_cuentas_edit_buyer", args=[orphan.pk]),
            {"customer_name": "Pepe", "sale_date": "no-es-fecha"},
            follow=True,
        )
        msgs = [str(m) for m in resp.context["messages"]]
        self.assertTrue(any("Fecha inv" in m for m in msgs), msgs)
        self.assertFalse(OrderItem.objects.filter(stock_item=orphan).exists())
        orphan.refresh_from_db()
        self.assertEqual(orphan.status, StockItem.Status.AVAILABLE)

    def test_manual_sale_telegram_sets_channel_and_username(self):
        """source=telegram + @user → Order.channel=TELEGRAM y telegram_username guardado."""
        from orders.models import Order, OrderItem

        orphan = StockItem.objects.create(
            product=self.product, plan=self.plan,
            credentials="Correo: tg@x.com\nContraseña: pp",
            status=StockItem.Status.AVAILABLE,
        )
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse("admin_cuentas_edit_buyer", args=[orphan.pk]),
            {
                "customer_name": "Cliente TG",
                "source": "telegram",
                "telegram_username": "@marco_lopez",  # con @, el backend lo limpia
            },
            follow=True,
        )
        msgs = [str(m) for m in resp.context["messages"]]
        self.assertTrue(any("Telegram" in m for m in msgs), msgs)
        oi = OrderItem.objects.get(stock_item=orphan)
        self.assertEqual(oi.order.channel, Order.Channel.TELEGRAM)
        self.assertEqual(oi.order.telegram_username, "marco_lopez")  # sin @

    def test_manual_sale_whatsapp_uses_manual_channel_with_notes(self):
        """source=whatsapp → Order.channel=MANUAL pero notes guarda 'Origen: WhatsApp'."""
        from orders.models import Order, OrderItem

        orphan = StockItem.objects.create(
            product=self.product, plan=self.plan,
            credentials="Correo: wa@x.com\nContraseña: pp",
            status=StockItem.Status.AVAILABLE,
        )
        self.client.force_login(self.staff)
        self.client.post(
            reverse("admin_cuentas_edit_buyer", args=[orphan.pk]),
            {
                "customer_name": "Cliente WA",
                "customer_whatsapp": "+51 911 222 333",
                "source": "whatsapp",
            },
            follow=True,
        )
        oi = OrderItem.objects.get(stock_item=orphan)
        self.assertEqual(oi.order.channel, Order.Channel.MANUAL)
        self.assertIn("WhatsApp", oi.order.notes)

    def test_manual_sale_telegram_inferred_from_username_alone(self):
        """Si llena @telegram pero no elige canal, se auto-detecta como Telegram."""
        from orders.models import Order, OrderItem

        orphan = StockItem.objects.create(
            product=self.product, plan=self.plan,
            credentials="Correo: auto@x.com\nContraseña: pp",
            status=StockItem.Status.AVAILABLE,
        )
        self.client.force_login(self.staff)
        self.client.post(
            reverse("admin_cuentas_edit_buyer", args=[orphan.pk]),
            {"telegram_username": "auto_user"},
            follow=True,
        )
        oi = OrderItem.objects.get(stock_item=orphan)
        self.assertEqual(oi.order.channel, Order.Channel.TELEGRAM)
        self.assertEqual(oi.order.telegram_username, "auto_user")

    def test_edit_existing_order_can_update_channel_and_telegram(self):
        """En modo edición, mandar source+telegram actualiza la Order existente."""
        from orders.models import Order

        # self.order y self.oi ya existen como un pedido WEB
        self.client.force_login(self.staff)
        self.client.post(
            reverse("admin_cuentas_edit_buyer", args=[self.item.pk]),
            {
                "source": "telegram",
                "telegram_username": "@cliente_existente",
            },
            follow=True,
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.channel, Order.Channel.TELEGRAM)
        self.assertEqual(self.order.telegram_username, "cliente_existente")

    def test_manual_sale_no_source_no_telegram_defaults_to_web(self):
        """Sin source y sin @telegram → canal WEB (se ve igual que una compra normal)."""
        from orders.models import Order, OrderItem

        orphan = StockItem.objects.create(
            product=self.product, plan=self.plan,
            credentials="Correo: mm@x.com\nContraseña: pp",
            status=StockItem.Status.AVAILABLE,
        )
        self.client.force_login(self.staff)
        self.client.post(
            reverse("admin_cuentas_edit_buyer", args=[orphan.pk]),
            {"customer_name": "Default Cliente"},
            follow=True,
        )
        oi = OrderItem.objects.get(stock_item=orphan)
        self.assertEqual(oi.order.channel, Order.Channel.WEB)
        self.assertEqual(oi.order.telegram_username, "")

    def test_dashboard_renders_source_select_and_telegram_field(self):
        """El modal incluye el <select name=source> y el input telegram_username."""
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_cuentas_dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="source"')
        self.assertContains(resp, 'name="telegram_username"')
        self.assertContains(resp, 'value="web"')
        self.assertContains(resp, 'value="telegram"')
        self.assertContains(resp, 'value="whatsapp"')

    def test_dashboard_renders_edit_button_for_sold_accounts(self):
        """El botón de editar cliente aparece en el dashboard para cuentas vendidas."""
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_cuentas_dashboard"))
        self.assertEqual(resp.status_code, 200)
        # El botón debe estar presente con la clase JS apropiada.
        self.assertContains(resp, "jh-cc-edit-buyer-btn")
        # El modal también debe estar renderizado.
        self.assertContains(resp, 'id="edit-buyer-modal"')
        self.assertContains(resp, 'name="customer_name"')
        self.assertContains(resp, 'name="sale_date"')

    def test_dashboard_renders_mobile_cards_layout(self):
        """En mobile se renderiza un layout de cards apiladas en paralelo a la tabla."""
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_cuentas_dashboard"))
        self.assertEqual(resp.status_code, 200)
        # Ambos contenedores existen (desktop table + mobile cards).
        self.assertContains(resp, 'jh-cc-table-desktop')
        self.assertContains(resp, 'jh-cc-cards-mobile')
        # Cada cuenta tiene un <article class="jh-cc-card">.
        self.assertContains(resp, 'jh-cc-card')
        # Las acciones también están renderizadas dentro de la card.
        self.assertContains(resp, 'jh-cc-card__actions')
        # El botón de editar cliente aparece DOS veces (uno en table, uno en card).
        # Buscamos por la clase específica del modal trigger.
        self.assertGreaterEqual(
            resp.content.decode().count("jh-cc-edit-buyer-btn"), 2,
            "El botón de editar cliente debe aparecer en table + card.",
        )

    def test_requested_profile_shown_as_main_badge_when_no_slot(self):
        """Si la cuenta no trae Perfil/PIN propios, el perfil/PIN del pedido
        manual se muestra como badge grande (igual a las demás), no solo como
        la línea chica 'Pidió'."""
        from orders.models import Order, OrderItem

        item = StockItem.objects.create(
            product=self.product, plan=self.plan,
            # Sin línea "Perfil:" / "PIN:" → no hay slot propio.
            credentials="Correo: zeno@x.com\nContraseña: pp",
            status=StockItem.Status.SOLD,
        )
        order = Order.objects.create(
            email="zeno@gmail.com", total=Decimal("20.00"),
            status=Order.Status.DELIVERED, paid_at=timezone.now(),
            channel=Order.Channel.WEB,
        )
        OrderItem.objects.create(
            order=order, product=self.product, plan=self.plan,
            product_name=self.product.name, plan_name=self.plan.name,
            unit_price=Decimal("20.00"), quantity=1, stock_item=item,
            requested_profile_name="Zeno", requested_pin="8143",
        )
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_cuentas_dashboard"))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        # Badge grande (mismo markup que el slot de las demás cuentas).
        self.assertIn('<span class="jh-cc-tag">Zeno</span>', html)
        self.assertIn(
            '<span class="jh-cc-tag jh-cc-tag--pin"><span class="jh-cc-tag__lbl">PIN</span>8143</span>',
            html,
        )
        # Regresión: el comentario de plantilla no debe filtrarse como texto
        # (los comentarios {# #} multilínea de Django se renderizan literales).
        self.assertNotIn("Sin slot", html)
        self.assertNotIn("{#", html)


class AdminInboxViewTests(TestCase):
    """Smoke test del feed unificado de bandeja del admin.

    Cubre regresión: usar el campo correcto ``ProductReview.author_name``
    (no ``author``). Crear una review pendiente fuerza la rama que antes
    crasheaba con AttributeError y rompía toda la bandeja.
    """

    def setUp(self):
        from catalog.models import ProductReview
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="staffinbox", password="x", is_staff=True, is_superuser=True,
        )
        self.cat = Category.objects.create(name="Streaming-inbox", slug="streaming-inbox")
        self.product = Product.objects.create(
            category=self.cat, name="Netflix Inbox", slug="netflix-inbox", is_active=True,
        )
        # Una review pendiente fuerza el render del item "review pendiente".
        ProductReview.objects.create(
            product=self.product,
            author_name="Cliente Test",
            email="c@example.com",
            rating=5,
            comment="Andaba todo perfecto",
            status=ProductReview.Status.PENDING,
        )

    def test_inbox_view_renders_with_pending_review(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_inbox"))
        self.assertEqual(resp.status_code, 200)
        # El nombre del autor debe aparecer en el feed (campo author_name).
        self.assertContains(resp, "Cliente Test")


class ProductAdminChangelistDesignTests(TestCase):
    """Verifica el rediseño de la lista de productos en el admin (chips)."""

    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="staffprods", password="x",
            is_staff=True, is_superuser=True,
        )
        cat = Category.objects.create(name="Streaming-list", slug="streaming-list")
        Product.objects.create(
            category=cat, name="ProdPerfil", slug="prodperfil",
            mode="perfil", is_active=True, is_featured=True,
            telegram_audience="customer", delivery_is_instant=False,
        )
        Product.objects.create(
            category=cat, name="ProdCompleta", slug="prodcompleta",
            mode="completa", is_active=True, is_featured=False,
            telegram_audience="both", delivery_is_instant=True,
        )
        Product.objects.create(
            category=cat, name="ProdLicencia", slug="prodlicencia",
            mode="licencia", is_active=False, is_featured=False,
            telegram_audience="none", delivery_is_instant=False,
        )

    def test_changelist_renders_compact_chips(self):
        self.client.force_login(self.staff)
        resp = self.client.get("/panel-virtualidadsp/catalog/product/")
        self.assertEqual(resp.status_code, 200)
        # Modo de venta como chips compactos
        self.assertContains(resp, "Por perfil")
        self.assertContains(resp, "Completa")
        self.assertContains(resp, "Licencia")
        # Telegram audience como chips compactos
        self.assertContains(resp, "Clientes")
        self.assertContains(resp, "Ambos")
        self.assertContains(resp, "No publicar")
        # Entrega como chip
        self.assertContains(resp, "Inmediata")
        self.assertContains(resp, "Manual")


class PlanAdminChangelistDesignTests(TestCase):
    """Verifica el rediseño de los listados de planes (cliente/distri/general)."""

    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="staffplans", password="x",
            is_staff=True, is_superuser=True,
        )
        cat = Category.objects.create(name="Streaming-plans", slug="streaming-plans")
        product = Product.objects.create(
            category=cat, name="Netflix Plans Test", slug="nflx-plans-test",
            is_active=True,
        )
        Plan.objects.create(
            product=product, name="1 mes",
            duration_days=30,
            price_customer=Decimal("35.00"),
            price_distributor=Decimal("0.00"),
            available_for_customer=True,
            available_for_distributor=False,
            is_active=True, low_stock_threshold=3,
        )
        Plan.objects.create(
            product=product, name="Perpetua",
            duration_days=0,
            price_customer=Decimal("0.00"),
            price_distributor=Decimal("55.00"),
            available_for_customer=False,
            available_for_distributor=True,
            is_active=False, low_stock_threshold=3,
        )

    def test_customer_plan_changelist_renders_chips(self):
        self.client.force_login(self.staff)
        resp = self.client.get("/panel-virtualidadsp/catalog/customerplan/")
        self.assertEqual(resp.status_code, 200)
        # Producto con celda combinada
        self.assertContains(resp, "Netflix Plans Test")
        # Duración chip
        self.assertContains(resp, "1 mes")
        # Precio chip cliente
        self.assertContains(resp, "$ 35.00")
        # Estado activo
        self.assertContains(resp, "Activo")
        # Chip class debe aparecer
        self.assertContains(resp, "jh-chip")

    def test_distributor_plan_changelist_renders_chips(self):
        self.client.force_login(self.staff)
        resp = self.client.get("/panel-virtualidadsp/catalog/distributorplan/")
        self.assertEqual(resp.status_code, 200)
        # Solo se ve el plan distri (Perpetua)
        self.assertContains(resp, "Perpetua")
        # Precio chip distri
        self.assertContains(resp, "$ 55.00")
        # Inactivo
        self.assertContains(resp, "Inactivo")

    def test_general_plan_changelist_renders_chips(self):
        self.client.force_login(self.staff)
        resp = self.client.get("/panel-virtualidadsp/catalog/plan/")
        self.assertEqual(resp.status_code, 200)
        # Ambos planes deben aparecer (cliente + distri)
        self.assertContains(resp, "Netflix Plans Test")
        self.assertContains(resp, "1 mes")
        self.assertContains(resp, "Perpetua")
        # Chips de precios ambos
        self.assertContains(resp, "$ 35.00")
        self.assertContains(resp, "$ 55.00")


class CachePerLanguageTests(TestCase):
    """Bug fix: el cache de `cache_for_anon` ahora incluye el idioma activo
    en la key. Antes, el primer visitante anónimo "envenenaba" el cache para
    todos los demás idiomas (cliente desde India que cambiaba a inglés veía
    igual la versión cacheada en español).
    """

    def test_cache_key_includes_active_language(self):
        """La cache key cambia según el idioma activo: dos visitas al
        mismo path con distinta cookie de idioma generan keys distintas."""
        from unittest.mock import patch, MagicMock
        from django.core.cache import cache as core_cache
        from django.test import RequestFactory
        from django.contrib.auth.models import AnonymousUser
        from django.http import HttpResponse
        from django.utils import translation
        from catalog.views import cache_for_anon

        core_cache.clear()
        captured_keys: list[str] = []
        rf = RequestFactory()

        original_get = core_cache.get

        def spy_get(key, *args, **kwargs):
            captured_keys.append(key)
            return original_get(key, *args, **kwargs)

        @cache_for_anon(timeout=60)
        def dummy(request):
            lang = translation.get_language()
            return HttpResponse(f"hello-{lang}")

        with patch.object(core_cache, "get", side_effect=spy_get):
            # Visita en español
            req_es = rf.get("/somepath/", SERVER_NAME="example.com")
            req_es.user = AnonymousUser()
            translation.activate("es")
            dummy(req_es)
            # Visita en inglés (mismo path)
            req_en = rf.get("/somepath/", SERVER_NAME="example.com")
            req_en.user = AnonymousUser()
            translation.activate("en")
            dummy(req_en)
            translation.deactivate()

        # Deben haberse intentado dos keys distintas (una por idioma).
        anon_keys = [k for k in captured_keys if k.startswith("anonview:")]
        self.assertEqual(len(set(anon_keys)), 2, f"keys={anon_keys}")
        self.assertTrue(any(":es:" in k for k in anon_keys), anon_keys)
        self.assertTrue(any(":en:" in k for k in anon_keys), anon_keys)


class CookieBannerLayoutTests(TestCase):
    """Bug fix: el banner de cookies en mobile se montaba sobre el
    bottom-nav (Inicio/Catálogo/...) y su fondo translúcido dejaba ver
    el hero detrás haciendo el texto ilegible. Ahora:
    - Fondo OPACO (gradient sólido `#14101f → #0c0a14`)
    - Posicionado ARRIBA del bottom-nav (`bottom: calc(96px + safe-area)`)
    - z-index 80 (por encima del nav que está en 45)
    """

    def test_banner_renders_above_bottom_nav_with_opaque_bg(self):
        """El banner usa la nueva clase `.jh-cookie-banner` con bottom
        offset que despeja el bottom-nav móvil, y su `__inner` tiene un
        background opaco (no la `.surface` semi-transparente)."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        # Clase y data-attrs nuevos
        self.assertIn('id="jh-cookie-banner"', html)
        self.assertIn("jh-cookie-banner__inner", html)
        self.assertIn('data-jh-consent="denied"', html)
        self.assertIn('data-jh-consent="granted"', html)
        # CSS: el banner se posiciona por encima del bottom-nav (96px+)
        self.assertIn("bottom: calc(96px + env(safe-area-inset-bottom))", html)
        # CSS: fondo opaco (no la .surface translúcida que provocaba el
        # bleed-through con el hero).
        self.assertIn("#14101f", html)
        # Z-index del banner > z-index del bottom-nav (45)
        self.assertIn("z-index: 80", html)

    def test_banner_uses_translated_strings(self):
        """Confirma que el banner sigue siendo traducible (no rompimos
        i18n al refactorizar el template). El test usa el idioma por
        defecto ("es") así que esperamos el texto en español."""
        resp = self.client.get("/")
        html = resp.content.decode()
        self.assertIn("Usamos cookies", html)
        self.assertIn("Aceptar todas", html)
        self.assertIn("Solo esenciales", html)
