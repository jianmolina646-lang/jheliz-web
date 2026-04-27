from django.contrib.syndication.views import Feed
from django.urls import reverse_lazy
from django.utils import timezone

from .models import BlogPost


class LatestPostsFeed(Feed):
    title = "Blog Jheliz"
    link = reverse_lazy("blog:list")
    description = "Guías, tips y noticias sobre cuentas premium de streaming y software original."

    def items(self):
        return BlogPost.objects.filter(
            status=BlogPost.Status.PUBLISHED,
            published_at__lte=timezone.now(),
        ).order_by("-published_at")[:20]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.excerpt

    def item_pubdate(self, item):
        return item.published_at

    def item_link(self, item):
        return item.get_absolute_url()
