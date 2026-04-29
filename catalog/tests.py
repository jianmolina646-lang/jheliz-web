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
        self.cat = Category.objects.create(name="Streaming", slug="streaming")
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
        self.admin = StockItemAdmin(StockItem, admin_site)

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

    def test_rejects_same_email_and_same_profile(self):
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
            "cuenta@netflix.com|otra-clave|Perfil 1|9999",
            product=self.product,
            plan=self.plan,
        )

        self.assertEqual(created, 0)
        self.assertEqual(skipped, 1)
        self.assertEqual(self.product.stock_items.count(), 1)

    def test_rejects_generic_account_when_same_email_already_exists(self):
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
            "cuenta@netflix.com|otra-clave",
            product=self.product,
            plan=self.plan,
        )

        self.assertEqual(created, 0)
        self.assertEqual(skipped, 1)
        self.assertEqual(self.product.stock_items.count(), 1)


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
        self.cat = Category.objects.create(name="Streaming", slug="streaming-mod")
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
        self.cat = Category.objects.create(name="Streaming", slug="streaming-pp")
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
        self.assertContains(resp, "S/ 8,00")
        self.assertNotContains(resp, "S/ 0,00")
