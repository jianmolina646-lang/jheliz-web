"""SEO sitemaps for Google Search Console & Bing Webmaster."""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import Category, Product


class StaticViewSitemap(Sitemap):
    """Pages without a model — home, FAQ, terms, etc."""

    priority = 0.8
    changefreq = "weekly"

    def items(self):
        return [
            "catalog:home",
            "catalog:products",
            "catalog:distributor",
            "catalog:tutorials",
            "catalog:warranty",
            "catalog:terms",
            "catalog:faq",
        ]

    def location(self, item):
        return reverse(item)


class CategorySitemap(Sitemap):
    priority = 0.7
    changefreq = "weekly"

    def items(self):
        return Category.objects.filter(is_active=True)

    def location(self, obj):
        return obj.get_absolute_url()


class ProductSitemap(Sitemap):
    priority = 0.9
    changefreq = "weekly"

    def items(self):
        return Product.objects.filter(is_active=True)

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return obj.get_absolute_url()


SITEMAPS = {
    "static": StaticViewSitemap,
    "categories": CategorySitemap,
    "products": ProductSitemap,
}
