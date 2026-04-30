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


def _audience_filter(user):
    """Oculta productos sin planes visibles para esta audiencia.

    Si el usuario es distribuidor aprobado, ve productos con al menos un plan
    activo visible para distribuidor. Si no, ve productos con al menos un plan
    activo visible para cliente final.
    """
    if user and getattr(user, "is_distributor", False):
        return Q(plans__is_active=True, plans__available_for_distributor=True)
    return Q(plans__is_active=True, plans__available_for_customer=True)


def home(request):
    featured = (
        Product.objects.filter(is_active=True, is_featured=True)
        .filter(_audience_filter(request.user))
        .select_related("category")
        .prefetch_related("plans")
        .distinct()
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
        .filter(_audience_filter(request.user))
        .select_related("category")
        .prefetch_related("plans")
        .distinct()
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
        .filter(_audience_filter(request.user))
        .select_related("category")
        .prefetch_related("plans")
        .distinct()
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


def _ensure_distributor(request):
    """Devuelve None si el usuario es distribuidor aprobado; redirige en otro caso."""
    user = request.user
    if getattr(user, "is_distributor", False):
        return None
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


@login_required
def distributor_panel(request):
    """Dashboard del distribuidor: métricas, próximos vencimientos y libro de ventas."""
    redirect_response = _ensure_distributor(request)
    if redirect_response is not None:
        return redirect_response

    from datetime import timedelta
    from decimal import Decimal
    from django.db.models import Sum, F, DecimalField

    user = request.user
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    from orders.models import OrderItem  # evita circular import en arranque

    base_items_qs = (
        OrderItem.objects
        .filter(order__user=user)
        .select_related("order", "product", "plan")
    )

    def _spend_in_period(start_dt):
        agg = base_items_qs.filter(order__created_at__gte=start_dt).aggregate(
            total=Sum(
                F("unit_price") * F("quantity"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
        )
        return agg["total"] or Decimal("0.00")

    spend_month = _spend_in_period(month_start)
    spend_year = _spend_in_period(year_start)

    # Ahorro = (precio público - precio que pagó) por cada item del periodo
    savings_month = Decimal("0.00")
    for item in base_items_qs.filter(order__created_at__gte=month_start):
        public_price = item.plan.price_customer or item.unit_price
        diff = (public_price - item.unit_price) * item.quantity
        if diff > 0:
            savings_month += diff

    # Próximos vencimientos (7 días) + recientes ya vencidos (24 h)
    soon_threshold = now + timedelta(days=7)
    overdue_threshold = now - timedelta(days=2)
    expiring_items = list(
        base_items_qs
        .filter(expires_at__isnull=False, expires_at__lte=soon_threshold, expires_at__gte=overdue_threshold)
        .order_by("expires_at")[:30]
    )

    # Top productos comprados (cantidad acumulada)
    top_products = (
        base_items_qs.values("product__name", "product__icon")
        .annotate(total_qty=Sum("quantity"))
        .order_by("-total_qty")[:5]
    )

    # Libro de ventas (últimos 50 items entregados)
    items_ledger = list(
        base_items_qs
        .exclude(delivered_credentials="")
        .order_by("-order__created_at")[:50]
    )

    pending_broken = base_items_qs.filter(reported_broken_at__isnull=False).count()

    ctx = {
        "spend_month": spend_month,
        "spend_year": spend_year,
        "savings_month": savings_month,
        "expiring_items": expiring_items,
        "top_products": top_products,
        "items_ledger": items_ledger,
        "items_total": base_items_qs.count(),
        "pending_broken": pending_broken,
        "now": now,
    }
    return render(request, "catalog/distributor_panel.html", ctx)


@login_required
def distributor_catalog(request):
    """Catálogo con precios mayoristas — solo para distribuidores aprobados."""
    redirect_response = _ensure_distributor(request)
    if redirect_response is not None:
        return redirect_response

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
        "catalog/distributor_catalog.html",
        {"products": products},
    )


@login_required
def distributor_edit_customer(request, item_id: int):
    """Guarda los datos del cliente final asociado a un OrderItem del distribuidor."""
    redirect_response = _ensure_distributor(request)
    if redirect_response is not None:
        return redirect_response
    if request.method != "POST":
        return redirect("catalog:distributor_panel")

    from orders.models import OrderItem
    item = get_object_or_404(
        OrderItem.objects.select_related("order"),
        pk=item_id,
        order__user=request.user,
    )
    item.final_customer_name = (request.POST.get("final_customer_name") or "").strip()[:120]
    raw_wa = (request.POST.get("final_customer_whatsapp") or "").strip()
    # Normaliza: deja solo dígitos y un + opcional al inicio
    normalized = "".join(ch for ch in raw_wa if ch.isdigit() or ch == "+")
    if normalized and not normalized.startswith("+"):
        normalized = "+" + normalized
    item.final_customer_whatsapp = normalized[:30]
    item.final_customer_notes = (request.POST.get("final_customer_notes") or "").strip()[:200]
    item.save(update_fields=[
        "final_customer_name",
        "final_customer_whatsapp",
        "final_customer_notes",
    ])
    messages.success(request, f"Cliente final actualizado para {item.product_name}.")
    return redirect("catalog:distributor_panel")


@login_required
def distributor_report_broken(request, item_id: int):
    """El distribuidor reporta que la cuenta dejó de funcionar.

    Marca el item como reportado, notifica al admin por Telegram + email y
    le devuelve un mensaje al distribuidor.
    """
    redirect_response = _ensure_distributor(request)
    if redirect_response is not None:
        return redirect_response
    if request.method != "POST":
        return redirect("catalog:distributor_panel")

    from orders.models import OrderItem
    from orders import telegram

    item = get_object_or_404(
        OrderItem.objects.select_related("order", "product"),
        pk=item_id,
        order__user=request.user,
    )
    note = (request.POST.get("note") or "").strip()[:200]
    item.reported_broken_at = timezone.now()
    item.reported_broken_note = note
    item.save(update_fields=["reported_broken_at", "reported_broken_note"])

    # Notificar al admin por Telegram (best-effort)
    try:
        text_lines = [
            "🚨 <b>Cuenta reportada como caída</b>",
            f"Distribuidor: {request.user.get_full_name() or request.user.username} ({request.user.email})",
            f"Producto: {item.product_name} — {item.plan_name}",
            f"Pedido: {str(item.order.uuid)[:8]}",
        ]
        if item.final_customer_name:
            text_lines.append(
                f"Cliente final: {item.final_customer_name}"
                + (f" ({item.final_customer_whatsapp})" if item.final_customer_whatsapp else "")
            )
        if note:
            text_lines.append(f"Nota: {note}")
        text_lines.append("")
        text_lines.append(
            "🔗 https://jhelizservicestv.xyz/jheliz-admin/orders/orderitem/"
            f"{item.pk}/change/"
        )
        telegram.notify_admin("\n".join(text_lines))
    except Exception:
        pass

    messages.success(
        request,
        "Reporte enviado. Te avisaremos por correo cuando reemplacemos la cuenta.",
    )
    return redirect("catalog:distributor_panel")


def tutorials(request):
    return render(request, "catalog/tutorials.html", {})


def terms(request):
    return render(request, "catalog/terms.html", {})


def warranty(request):
    return render(request, "catalog/warranty.html", {})
