from __future__ import annotations

from django.core.paginator import Paginator
from django.db.models import F
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import BlogCategory, BlogPost
from .markdown import render_markdown


def _published_qs():
    return BlogPost.objects.filter(
        status=BlogPost.Status.PUBLISHED,
        published_at__lte=timezone.now(),
    ).select_related("category", "author")


def post_list(request, category_slug: str | None = None):
    qs = _published_qs()
    category = None
    cat_slug = category_slug or request.GET.get("categoria")
    if cat_slug:
        category = get_object_or_404(BlogCategory, slug=cat_slug)
        qs = qs.filter(category=category)
    paginator = Paginator(qs, 9)
    page = paginator.get_page(request.GET.get("page"))
    featured = None
    if not category and page.number == 1:
        featured = _published_qs().filter(is_featured=True).first()
        if featured:
            page.object_list = [p for p in page.object_list if p.id != featured.id]
    categories = BlogCategory.objects.all()
    return render(request, "blog/list.html", {
        "page_obj": page,
        "featured": featured,
        "category": category,
        "categories": categories,
    })


def post_detail(request, slug: str):
    post = get_object_or_404(_published_qs(), slug=slug)
    BlogPost.objects.filter(pk=post.pk).update(views_count=F("views_count") + 1)
    related_posts = (
        _published_qs()
        .exclude(pk=post.pk)
        .filter(category=post.category)
        if post.category else _published_qs().exclude(pk=post.pk)
    )[:3]
    return render(request, "blog/detail.html", {
        "post": post,
        "body_html": render_markdown(post.body),
        "related_posts": related_posts,
        "related_products": list(post.related_products.filter(is_active=True)[:3]),
    })
