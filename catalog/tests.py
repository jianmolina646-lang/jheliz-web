from datetime import timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

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
