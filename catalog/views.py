from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from .models import Category, Product


def home(request):
    featured = (
        Product.objects.filter(is_active=True, is_featured=True)
        .select_related("category")
        .prefetch_related("plans")
    )
    top_categories = Category.objects.filter(is_active=True)[:6]
    return render(
        request,
        "catalog/home.html",
        {"featured_products": featured, "top_categories": top_categories},
    )


def product_list(request):
    q = request.GET.get("q", "").strip()
    category_slug = request.GET.get("categoria")
    products = (
        Product.objects.filter(is_active=True)
        .select_related("category")
        .prefetch_related("plans")
    )
    if q:
        products = products.filter(
            Q(name__icontains=q) | Q(short_description__icontains=q)
        )
    category = None
    if category_slug:
        category = get_object_or_404(Category, slug=category_slug, is_active=True)
        products = products.filter(category=category)
    categories = Category.objects.filter(is_active=True)
    return render(
        request,
        "catalog/product_list.html",
        {
            "products": products,
            "categories": categories,
            "active_category": category,
            "q": q,
        },
    )


def category_detail(request, slug: str):
    category = get_object_or_404(Category, slug=slug, is_active=True)
    products = (
        category.products.filter(is_active=True)
        .select_related("category")
        .prefetch_related("plans")
    )
    categories = Category.objects.filter(is_active=True)
    return render(
        request,
        "catalog/product_list.html",
        {
            "products": products,
            "categories": categories,
            "active_category": category,
            "q": "",
        },
    )


def product_detail(request, slug: str):
    product = get_object_or_404(
        Product.objects.select_related("category").prefetch_related("plans"),
        slug=slug,
        is_active=True,
    )
    plans = product.active_plans(request.user)
    return render(
        request,
        "catalog/product_detail.html",
        {"product": product, "plans": plans},
    )


def distributor_landing(request):
    categories = Category.objects.filter(
        is_active=True, audience__in=["distribuidor", "ambos"],
    )
    return render(
        request, "catalog/distributor.html", {"categories": categories},
    )


def tutorials(request):
    return render(request, "catalog/tutorials.html", {})


def terms(request):
    return render(request, "catalog/terms.html", {})


def warranty(request):
    return render(request, "catalog/warranty.html", {})
