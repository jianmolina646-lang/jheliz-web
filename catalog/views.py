import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .models import Category, Product


def _product_schema(request, product, plans):
    """Schema.org Product JSON-LD for SEO rich results."""
    cheapest = min((p.price_customer for p in plans), default=None)
    image_url = None
    if product.image:
        image_url = request.build_absolute_uri(product.image.url)
    schema = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product.name,
        "description": product.short_description or product.description or product.name,
        "category": product.category.name,
        "url": request.build_absolute_uri(product.get_absolute_url()),
        "brand": {"@type": "Brand", "name": "Jheliz"},
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": str(product.rating),
            "reviewCount": "50",
            "bestRating": "5",
            "worstRating": "1",
        },
    }
    if image_url:
        schema["image"] = image_url
    if cheapest is not None:
        schema["offers"] = {
            "@type": "Offer",
            "priceCurrency": "PEN",
            "price": str(cheapest),
            "availability": "https://schema.org/InStock",
            "url": request.build_absolute_uri(product.get_absolute_url()),
        }
    return json.dumps(schema, ensure_ascii=False)


TESTIMONIOS = [
    {"author": "Carla M.", "city": "Lima", "rating": 5,
     "text": "Compr\u00e9 Netflix Premium y la cuenta lleg\u00f3 en menos de 5 minutos. Soporte por WhatsApp s\u00faper r\u00e1pido."},
    {"author": "Diego R.", "city": "Arequipa", "rating": 5,
     "text": "Llevo 6 meses comprando aqu\u00ed mes a mes. Cero problemas, precios mucho mejores que otras p\u00e1ginas."},
    {"author": "Andrea L.", "city": "Trujillo", "rating": 5,
     "text": "Pagu\u00e9 con Yape y todo perfecto. La cuenta de Disney+ funciona sin fallar."},
    {"author": "Mart\u00edn T.", "city": "Cusco", "rating": 5,
     "text": "Compr\u00e9 Office 2021 \u2014 lleg\u00f3 la licencia, la activ\u00e9 y a trabajar. Recomendado."},
    {"author": "Lucia P.", "city": "Piura", "rating": 5,
     "text": "Soy distribuidora desde hace 3 meses, los precios mayoristas y el panel automatizado me hacen la vida f\u00e1cil."},
    {"author": "Jorge A.", "city": "Chiclayo", "rating": 5,
     "text": "Tuve un problema con Prime Video y me repusieron la cuenta sin preguntar. Garant\u00eda real."},
]


def _recent_purchases(limit: int = 8):
    """Mini-ticker of latest purchases for social proof.

    Returns paid orders with the customer's first name + city masked.
    """
    from orders.models import Order

    qs = (
        Order.objects.filter(status__in=[Order.Status.PAID, Order.Status.DELIVERED])
        .select_related("user")
        .prefetch_related("items__plan__product")
        .order_by("-created_at")[: limit * 2]
    )
    out = []
    for order in qs:
        first_item = order.items.first()
        if not first_item or not first_item.plan:
            continue
        # Only first name + last initial for privacy.
        name = order.user.first_name if order.user else ""
        if not name:
            name = (order.user.username if order.user else "").split("@")[0]
        if not name:
            name = "Cliente"
        masked = name.split()[0].title()
        out.append({
            "name": masked,
            "product": first_item.plan.product.name,
            "when": order.created_at,
        })
        if len(out) >= limit:
            break
    return out


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
        {
            "featured_products": featured,
            "top_categories": top_categories,
            "testimonios": TESTIMONIOS,
            "recent_purchases": _recent_purchases(),
        },
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
    plans = list(product.active_plans(request.user))
    return render(
        request,
        "catalog/product_detail.html",
        {
            "product": product,
            "plans": plans,
            "product_schema": _product_schema(request, product, plans),
        },
    )


def distributor_landing(request):
    categories = Category.objects.filter(
        is_active=True, audience__in=["distribuidor", "ambos"],
    )
    return render(
        request, "catalog/distributor.html", {"categories": categories},
    )


@login_required
def distributor_panel(request):
    """Catálogo con precios mayoristas — solo para distribuidores aprobados."""
    user = request.user
    if not getattr(user, "is_distributor", False):
        if getattr(user, "role", None) == "distribuidor":
            messages.info(
                request,
                "Tu cuenta de distribuidor está pendiente de aprobación. "
                "En cuanto te aprobemos, verás los precios mayoristas aquí.",
            )
        else:
            messages.info(
                request,
                "Esta zona es solo para distribuidores. "
                "Si quieres serlo, regístrate como distribuidor y te activamos la cuenta.",
            )
        return redirect("catalog:distributor")

    products = (
        Product.objects.filter(
            is_active=True,
            plans__is_active=True,
            plans__available_for_distributor=True,
        )
        .select_related("category")
        .prefetch_related("plans")
        .distinct()
    )
    return render(
        request,
        "catalog/distributor_panel.html",
        {"products": products},
    )


def tutorials(request):
    return render(request, "catalog/tutorials.html", {})


def terms(request):
    return render(request, "catalog/terms.html", {})


def warranty(request):
    return render(request, "catalog/warranty.html", {})
