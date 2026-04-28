from django.contrib.sitemaps import Sitemap
from django.utils import timezone

from .models import BlogPost


class BlogPostSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return BlogPost.objects.filter(
            status=BlogPost.Status.PUBLISHED,
            published_at__lte=timezone.now(),
        )

    def lastmod(self, obj):
        return obj.updated_at
