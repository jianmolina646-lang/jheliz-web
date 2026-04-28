import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from django.db.models import Avg, Count
from django.utils import timezone

from .forms import ProductReviewForm
from .models import Category, Plan, Product, ProductReview, Testimonial


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


def _testimonios():
    """Return published testimonios from the DB."""
    return Testimonial.objects.filter(is_published=True)[:9]


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
    # Productos destacados con precio mínimo desde — para hero strip
    starter_products = (
        Product.objects.filter(
            is_active=True,
            plans__is_active=True,
            plans__available_for_customer=True,
        )
        .select_related("category")
        .prefetch_related("plans")
        .order_by("-is_featured", "name")
        .distinct()[:6]
    )
    starter_strip = []
    for p in starter_products:
        plans = [pl for pl in p.plans.all() if pl.is_active and pl.available_for_customer and pl.price_customer > 0]
        if not plans:
            continue
        cheapest = min(plans, key=lambda pl: pl.price_customer)
        starter_strip.append({
            "product": p,
            "from_price": cheapest.price_customer,
        })
    return render(
        request,
        "catalog/home.html",
        {
            "featured_products": featured,
            "top_categories": top_categories,
            "testimonios": _testimonios(),
            "recent_purchases": _recent_purchases(),
            "starter_strip": starter_strip,
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

    reviews_qs = (
        product.reviews
        .filter(status=ProductReview.Status.APPROVED)
        .order_by("-created_at")
    )
    review_stats = reviews_qs.aggregate(
        avg=Avg("rating"), count=Count("id"),
    )
    avg_rating = float(review_stats["avg"] or product.rating or 5)
    rating_breakdown = []
    total = review_stats["count"] or 0
    for star in range(5, 0, -1):
        n = reviews_qs.filter(rating=star).count()
        pct = int(round((n / total) * 100)) if total else 0
        rating_breakdown.append({"star": star, "count": n, "pct": pct})

    return render(
        request,
        "catalog/product_detail.html",
        {
            "product": product,
            "plans": plans,
            "product_schema": _product_schema(request, product, plans),
            "reviews": list(reviews_qs[:12]),
            "review_count": total,
            "avg_rating": round(avg_rating, 1),
            "rating_breakdown": rating_breakdown,
        },
    )


def submit_review(request, token: str):
    """Formulario de rese\u00f1a accesible v\u00eda magic link enviado al cliente."""
    review = get_object_or_404(
        ProductReview.objects.select_related("product", "order"),
        token=token,
    )
    if review.status == ProductReview.Status.APPROVED:
        messages.info(request, "Esta rese\u00f1a ya fue publicada. \u00a1Gracias!")
        return redirect("catalog:review_thanks")

    if request.method == "POST":
        form = ProductReviewForm(request.POST, request.FILES, instance=review)
        if form.is_valid():
            review = form.save(commit=False)
            review.status = ProductReview.Status.PENDING
            if review.order_id:
                review.is_verified = True
            review.token_used_at = timezone.now()
            review.save()
            return redirect("catalog:review_thanks")
    else:
        form = ProductReviewForm(instance=review)

    return render(
        request,
        "catalog/review_submit.html",
        {
            "form": form,
            "review": review,
            "product": review.product,
        },
    )


def review_thanks(request):
    return render(request, "catalog/review_thanks.html", {})


def distributor_landing(request):
    categories = Category.objects.filter(
        is_active=True, audience__in=["distribuidor", "ambos"],
    )
    # Planes destacados para mostrar margen al visitante
    plans_qs = (
        Plan.objects.filter(
            is_active=True,
            available_for_distributor=True,
            price_distributor__gt=0,
        )
        .select_related("product", "product__category")
        .order_by("-product__is_featured", "duration_days")[:4]
    )
    sample_plans = []
    for p in plans_qs:
        diff = p.price_customer - p.price_distributor
        pct = int(round(diff / p.price_customer * 100)) if p.price_customer else 0
        sample_plans.append({
            "product_name": p.product.name,
            "name": p.name,
            "price_customer": p.price_customer,
            "price_distributor": p.price_distributor,
            "savings_amount": diff,
            "savings_pct": pct,
        })
    total_active_products = Product.objects.filter(is_active=True).count()
    return render(
        request,
        "catalog/distributor.html",
        {
            "categories": categories,
            "sample_plans": sample_plans,
            "total_active_products": total_active_products,
        },
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


def privacy(request):
    """Política de privacidad y protección de datos personales (Ley 29733)."""
    return render(request, "catalog/privacy.html", {})


def cookies_policy(request):
    """Política de cookies."""
    return render(request, "catalog/cookies.html", {})


def reclamaciones(request):
    """Libro de reclamaciones digital (Indecopi).

    GET → muestra el formulario público.
    POST → valida, guarda, envía email al cliente y al admin, muestra confirmación.
    """
    from .forms import ReclamacionForm
    from .models import Reclamacion

    if request.method == "POST":
        form = ReclamacionForm(request.POST)
        if form.is_valid():
            obj: Reclamacion = form.save(commit=False)
            obj.ip_address = (
                request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
                or request.META.get("REMOTE_ADDR")
            )
            obj.user_agent = request.META.get("HTTP_USER_AGENT", "")[:300]
            obj.save()
            try:
                _send_reclamacion_emails(obj)
            except Exception:
                pass
            return render(
                request, "catalog/reclamaciones_ok.html",
                {"reclamacion": obj},
            )
    else:
        initial = {}
        if request.user.is_authenticated:
            initial["nombre"] = request.user.get_full_name() or request.user.username
            initial["email"] = request.user.email
        form = ReclamacionForm(initial=initial)
    return render(
        request, "catalog/reclamaciones.html",
        {"form": form},
    )


def _send_reclamacion_emails(obj):
    """Manda copia al cliente y notifica al admin."""
    from django.conf import settings as dj_settings
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string

    site_name = "Jheliz"
    subject = f"Confirmación reclamación #{obj.numero} — {site_name}"
    ctx = {"reclamacion": obj, "site_name": site_name}

    # Email al cliente
    try:
        body = render_to_string("emails/reclamacion_recibida.txt", ctx)
        html = render_to_string("emails/reclamacion_recibida.html", ctx)
    except Exception:
        body = (
            f"Hola {obj.nombre},\n\n"
            f"Recibimos tu reclamación #{obj.numero}. "
            f"Tenemos hasta 30 días calendario para responder.\n\n"
            f"Detalle: {obj.detalle}\n\n"
            f"Gracias.\n{site_name}"
        )
        html = body.replace("\n", "<br>")
    msg = EmailMultiAlternatives(
        subject, body,
        getattr(dj_settings, "DEFAULT_FROM_EMAIL", "ventas@jhelizservicestv.xyz"),
        [obj.email],
    )
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=True)

    # Email al admin
    admin_email = getattr(dj_settings, "DEFAULT_FROM_EMAIL", None)
    if admin_email:
        admin_msg = (
            f"Nueva reclamación recibida:\n\n"
            f"Número: {obj.numero}\n"
            f"Cliente: {obj.nombre} ({obj.email}, {obj.telefono})\n"
            f"Tipo: {obj.get_tipo_display()}\n"
            f"Monto: {obj.monto or '—'}\n"
            f"Pedido: {obj.pedido_referencia or '—'}\n\n"
            f"Detalle:\n{obj.detalle}\n\n"
            f"Pedido del consumidor:\n{obj.pedido_consumidor}\n\n"
            f"Vence: {obj.vence_at.strftime('%d/%m/%Y')}"
        )
        EmailMultiAlternatives(
            f"[Reclamación nueva] #{obj.numero} — {obj.nombre}",
            admin_msg,
            admin_email,
            [admin_email],
        ).send(fail_silently=True)
