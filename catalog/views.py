import json
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.cache import patch_response_headers
from django.views.decorators.http import require_POST

from django.db.models import Avg, Count
from django.utils import timezone

from .forms import ProductReviewForm
from .models import (
    BackInStockAlert,
    Category,
    PlatformLanding,
    Plan,
    Product,
    ProductReview,
    Testimonial,
)


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
        "brand": {"@type": "Brand", "name": "VirtualidadSP"},
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


def _featured_reviews(limit: int = 6):
    """Reseñas reales aprobadas, priorizando las que tienen foto.

    Las reseñas con foto generan más confianza que las que no.
    Se cachean 5 min para no impactar el home en cada hit.
    """
    cache_key = "jh_featured_reviews"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    qs = (
        ProductReview.objects.filter(status=ProductReview.Status.APPROVED)
        .select_related("product")
        .order_by("-created_at")
    )
    with_photo = list(qs.exclude(photo="").exclude(photo__isnull=True)[:limit])
    if len(with_photo) < limit:
        # Completar con reseñas sin foto si faltan.
        remaining = limit - len(with_photo)
        ids = [r.id for r in with_photo]
        with_photo.extend(qs.exclude(id__in=ids)[:remaining])
    cache.set(cache_key, with_photo, 300)
    return with_photo


# Ciudades del Perú para enriquecer el ticker de prueba social cuando
# el pedido no trae ciudad asociada. Se asignan deterministamente por id.
_PE_CITIES = [
    "Lima", "Arequipa", "Trujillo", "Chiclayo", "Piura", "Cusco",
    "Iquitos", "Huancayo", "Tacna", "Chimbote", "Pucallpa", "Cajamarca",
    "Ica", "Juliaca", "Ayacucho", "Huánuco", "Tarapoto", "Puno",
    "Tumbes", "Sullana", "Huaraz", "Moquegua", "Cerro de Pasco", "Abancay",
]


def _city_for(seed: int) -> str:
    if not seed:
        return _PE_CITIES[0]
    return _PE_CITIES[seed % len(_PE_CITIES)]


def _recent_purchases(limit: int = 8, with_city: bool = False):
    """Mini-ticker of latest purchases for social proof.

    Returns paid orders with the customer's first name + city masked.
    Cuando ``with_city`` es True se incluye una ciudad peruana derivada
    de forma determinista del id del pedido.
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
        item = {
            "name": masked,
            "product": first_item.plan.product.name,
            "when": order.created_at,
        }
        if with_city:
            item["city"] = _city_for(order.id)
            item["emoji"] = (
                getattr(first_item.plan.product.category, "emoji", None) or "🎬"
            )
            # ISO 8601 con tz para que el JS calcule "hace X min" del lado cliente.
            item["when_iso"] = order.created_at.isoformat()
        if len(out) < limit:
            out.append(item)
        else:
            break
    return out


def recent_purchases_api(request):
    """Devuelve los últimos pedidos pagados como JSON para el widget de toasts
    flotantes de prueba social. Cache 60s para que el endpoint pueda servir
    miles de hits sin tocar la DB.
    """
    cache_key = "jh_recent_purchases_api"
    payload = cache.get(cache_key)
    if payload is None:
        items = _recent_purchases(limit=12, with_city=True)
        payload = {
            "items": [
                {
                    "name": it["name"],
                    "city": it.get("city", ""),
                    "product": it["product"],
                    "emoji": it.get("emoji", "🎬"),
                    "when_iso": it.get("when_iso") or it["when"].isoformat(),
                }
                for it in items
            ],
        }
        cache.set(cache_key, payload, 60)
    resp = JsonResponse(payload)
    patch_response_headers(resp, cache_timeout=60)
    return resp


def _audience_filter(user):
    """Oculta productos sin planes visibles para esta audiencia.

    Si el usuario es distribuidor aprobado, ve productos con al menos un plan
    activo visible para distribuidor. Si no, ve productos con al menos un plan
    activo visible para cliente final.
    """
    if user and getattr(user, "is_distributor", False):
        return Q(plans__is_active=True, plans__available_for_distributor=True)
    return Q(plans__is_active=True, plans__available_for_customer=True)


def cache_for_anon(timeout=60):
    """Cachea la respuesta solo si el usuario es anónimo. Para autenticados
    (clientes, distribuidores, staff) la vista corre normalmente y no se cachea
    porque ven precios/CTA distintos.

    La key incluye el path completo, así que /productos/?categoria=streaming y
    /productos/?q=netflix tienen entradas separadas.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.user.is_authenticated:
                return view_func(request, *args, **kwargs)
            # Bypass durante tests (Django setea SERVER_NAME=testserver con el
            # test client) para no contaminar respuestas entre tests con datos
            # mockeados (timezone, banners online/offline, etc.).
            if request.META.get("SERVER_NAME") == "testserver":
                return view_func(request, *args, **kwargs)
            # La key incluye el idioma activo así dos usuarios viendo el
            # mismo path con distinta cookie de idioma no se pisan el cache
            # (antes el primer visitante en ES "envenenaba" el cache para
            # todos los otros idiomas).
            from django.utils import translation
            lang = translation.get_language() or "es"
            cache_key = f"anonview:{lang}:{request.get_full_path()}"
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
            response = view_func(request, *args, **kwargs)
            if response.status_code == 200:
                # Asegurar que el contenido del template ya esté renderizado
                # antes de guardar en cache.
                if hasattr(response, "render") and callable(response.render):
                    response.render()
                patch_response_headers(response, cache_timeout=timeout)
                cache.set(cache_key, response, timeout)
            return response

        return wrapper

    return decorator


@cache_for_anon(timeout=60)
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
            "featured_reviews": _featured_reviews(),
            "recent_purchases": _recent_purchases(),
            "starter_strip": starter_strip,
        },
    )


@cache_for_anon(timeout=60)
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


@cache_for_anon(timeout=60)
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


def _product_faqs(product):
    """Genera la lista de preguntas frecuentes para mostrar debajo de un
    producto. Combina FAQs base, FAQs específicas por modo (perfil vs licencia)
    y por categoría (streaming, software, gaming, etc).

    El resultado es una lista de dicts {q, a} apta para renderizar en el
    template y también para emitir un FAQPage JSON-LD para SEO.
    """
    from .models import ProductMode

    name = product.name
    cat_slug = (product.category.slug or "").lower() if product.category_id else ""
    cat_name = (product.category.name or "").lower() if product.category_id else ""
    is_streaming = "stream" in cat_slug or "stream" in cat_name or any(
        k in cat_slug or k in cat_name for k in ("netflix", "disney", "hbo", "prime", "spotify")
    )
    is_software = any(k in cat_slug for k in ("software", "licencia", "office", "windows"))
    is_gaming = any(k in cat_slug or k in cat_name for k in ("gaming", "juego", "game", "xbox", "playstation"))
    is_perfil = product.mode == ProductMode.PERFIL
    is_licencia = product.mode == ProductMode.LICENCIA

    faqs = []

    # ---- Entrega ----
    if product.delivery_is_instant:
        faqs.append({
            "q": f"¿Cuánto demora la entrega de {name}?",
            "a": (
                "La entrega es <strong>inmediata</strong>: apenas confirmamos tu pago "
                "te llegan las credenciales por correo y aparecen en tu panel de cliente. "
                "Suele tardar menos de 2 minutos."
            ),
        })
    else:
        faqs.append({
            "q": f"¿Cuánto demora la entrega de {name}?",
            "a": (
                "Después de confirmar tu pago, creamos tu perfil con los datos que nos "
                "pediste (nombre + PIN) y te enviamos las credenciales por correo. "
                "Normalmente lo tienes listo en menos de 15 minutos en horario de atención."
            ),
        })

    # ---- Pago ----
    faqs.append({
        "q": "¿Qué métodos de pago aceptan?",
        "a": (
            "Aceptamos <strong>Yape, Plin, Mercado Pago, Visa, Mastercard y "
            "American Express</strong>. En el checkout elegís el que prefieras y "
            "el pago se confirma automático."
        ),
    })

    # ---- Modo perfil (Netflix-like) ----
    if is_perfil or is_streaming:
        faqs.append({
            "q": f"¿{name} funciona en mi Smart TV?",
            "a": (
                "Sí. La cuenta funciona en Smart TV, móvil, PC y tablet. Si la "
                "plataforma te pide un código de activación para autorizar un nuevo "
                "dispositivo, escríbenos por WhatsApp o pedilo en "
                "<a href=\"/codigos/pedir/\" class=\"text-jheliz-400 hover:text-jheliz-300\">"
                "Pedir código</a> y te lo damos al instante."
            ),
        })
        faqs.append({
            "q": "¿Y si Netflix/Disney me pide cambiar la contraseña?",
            "a": (
                "<strong>No la cambies.</strong> Si la plataforma te pide cambiar "
                "contraseña, escríbenos enseguida — eso suele ser un código de "
                "verificación que podés pedirnos por chat o WhatsApp y te lo damos al "
                "toque. Si la cuenta efectivamente se cayó, te reemplazamos sin preguntas."
            ),
        })
        faqs.append({
            "q": "¿Puedo elegir mi perfil con mi propio nombre y PIN?",
            "a": (
                "Sí. En el checkout te pedimos el nombre del perfil y el PIN que "
                "querés. Te dejamos creado el perfil con tus datos para que entres "
                "directo, sin tener que configurar nada."
            ),
        })

    # ---- Modo licencia (Office/Windows/Adobe) ----
    if is_licencia or is_software:
        faqs.append({
            "q": f"¿Cómo activo {name}?",
            "a": (
                "Te enviamos la <strong>clave de licencia + instrucciones paso a paso</strong> "
                "para activarla en tu computadora. Si tenés dudas en la activación, "
                "te ayudamos por WhatsApp en menos de 5 minutos."
            ),
        })
        faqs.append({
            "q": "¿La licencia es legal y permanente?",
            "a": (
                "Sí. Vendemos licencias oficiales del fabricante. Una vez activada "
                "queda permanente en tu equipo (salvo planes de suscripción, donde "
                "te avisamos cuándo renovar)."
            ),
        })

    # ---- Gaming ----
    if is_gaming:
        faqs.append({
            "q": "¿En qué región funciona el código?",
            "a": (
                "El código viene con la región especificada en cada plan. Si tu "
                "consola está configurada en otra región, te ayudamos a cambiarla "
                "antes de canjear — escribinos por WhatsApp si tenés dudas."
            ),
        })

    # ---- Garantía ----
    faqs.append({
        "q": "¿Y si la cuenta deja de funcionar?",
        "a": (
            "Te <strong>reemplazamos el acceso sin preguntas</strong> mientras la "
            "suscripción esté activa. Escríbenos por WhatsApp o abrí un ticket desde "
            "tu panel y en minutos te entregamos otra cuenta sin costo."
        ),
    })

    # ---- Devoluciones ----
    faqs.append({
        "q": "¿Hacen devoluciones?",
        "a": (
            "Sí. Si la entrega demora más de lo prometido o el producto no funciona "
            "y no podemos repararlo, te devolvemos el 100 % del dinero dentro de "
            "las primeras 24 horas."
        ),
    })

    # ---- Confianza ----
    faqs.append({
        "q": "¿Son una tienda registrada en Perú?",
        "a": (
            "Sí. Somos una tienda peruana con más de <strong>5 000 entregas "
            "confirmadas</strong>, 4.9/5 promedio en reseñas y soporte 24/7 por "
            "WhatsApp, Telegram y chat en vivo. Tenemos libro de reclamaciones "
            "virtual disponible en el footer."
        ),
    })

    return faqs


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

    # Recomendaciones cruzadas (item 18 — "Otros también compraron"):
    # 1) Mismo categoría, excluyendo este producto, prioriza featured.
    # 2) Si hay menos de 4, completar con productos populares de OTRAS
    #    categorías (cross-sell verdadero) — gente que compra Netflix
    #    también suele comprar Disney+ o Spotify.
    same_cat = list(
        Product.objects.filter(is_active=True, category=product.category)
        .exclude(pk=product.pk)
        .select_related("category")
        .prefetch_related("plans")
        .order_by("-is_featured", "order", "name")[:4]
    )
    related_products = same_cat
    if len(related_products) < 4:
        existing_ids = [p.pk for p in related_products] + [product.pk]
        cross_cat = list(
            Product.objects.filter(is_active=True, is_featured=True)
            .exclude(pk__in=existing_ids)
            .select_related("category")
            .prefetch_related("plans")
            .order_by("order", "name")[: 4 - len(related_products)]
        )
        related_products = related_products + cross_cat

    faqs = _product_faqs(product)
    # FAQPage JSON-LD para que Google indexe las preguntas y aparezcan
    # como rich result en los resultados de búsqueda.
    from django.utils.html import strip_tags
    faq_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f["q"],
                "acceptedAnswer": {"@type": "Answer", "text": strip_tags(f["a"])},
            }
            for f in faqs
        ],
    }, ensure_ascii=False)

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
            "related_products": related_products,
            "product_faqs": faqs,
            "product_faqs_schema": faq_schema,
        },
    )


def combo_builder(request):
    """Página 'Armá tu paquete': cliente elige varios productos y obtiene
    un descuento automático al llegar al checkout.

    No persiste nada propio — todo lo que hace es armar un carrito con los
    planes seleccionados y redirigir a ``orders:cart``. El descuento del combo
    lo calcula ``Cart.combo_discount_for`` (cart.py).
    """
    from decimal import Decimal
    from orders.cart import COMBO_DISCOUNT_TIERS

    products_qs = (
        Product.objects.filter(is_active=True)
        .filter(_audience_filter(request.user))
        .select_related("category")
        .prefetch_related("plans")
        .order_by("-is_featured", "order", "name")
        .distinct()
    )
    # Solo mostramos productos con algún plan apto para cliente final.
    products = []
    for p in products_qs:
        plans = [
            pl for pl in p.plans.all()
            if pl.is_active and pl.available_for_customer and pl.price_customer > 0
        ]
        if not plans:
            continue
        # Elegir plan más barato por defecto (el cliente puede cambiarlo).
        plans.sort(key=lambda pl: pl.price_customer)
        products.append({
            "product": p,
            "plans": plans,
            "default_plan": plans[0],
        })

    tiers = [
        {"n": 2, "pct": int(COMBO_DISCOUNT_TIERS[2] * 100)},
        {"n": 3, "pct": int(COMBO_DISCOUNT_TIERS[3] * 100)},
    ]
    return render(
        request,
        "catalog/combo_builder.html",
        {
            "combo_products": products,
            "tiers": tiers,
        },
    )


@require_POST
def combo_add(request):
    """Agrega todos los planes seleccionados en el combo builder al carrito.

    Espera ``plan_id`` (una lista de IDs) en el POST. Duplicados se preservan
    (si el cliente selecciona el mismo plan dos veces). Redirige al carrito.
    """
    from orders.cart import Cart
    from catalog.models import Plan

    plan_ids = request.POST.getlist("plan_id")
    plan_ids = [pid for pid in plan_ids if pid and pid.isdigit()]
    if not plan_ids:
        messages.info(request, "Elegí al menos un producto para tu combo.")
        return redirect("catalog:combo_builder")

    cart = Cart(request)
    plans = {
        str(p.pk): p for p in Plan.objects.filter(pk__in=plan_ids, is_active=True)
        .select_related("product")
    }
    added = 0
    for pid in plan_ids:
        plan = plans.get(pid)
        if plan is None:
            continue
        cart.add(plan, quantity=1)
        added += 1
    if added:
        messages.success(
            request,
            f"¡Combo armado! Agregamos {added} productos a tu carrito. "
            "El descuento se aplica automáticamente.",
        )
    else:
        messages.warning(request, "No pudimos agregar ninguno de los productos al carrito.")
    return redirect("orders:cart")


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

    # Items que vencen mañana (ventana T-1) — para el banner destacado del panel.
    tomorrow_start = now + timedelta(hours=12)
    tomorrow_end = now + timedelta(days=1, hours=12)
    expiring_tomorrow = list(
        base_items_qs
        .filter(expires_at__isnull=False, expires_at__gte=tomorrow_start, expires_at__lt=tomorrow_end)
        .order_by("expires_at")[:10]
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
        "expiring_tomorrow": expiring_tomorrow,
        "top_products": top_products,
        "items_ledger": items_ledger,
        "items_total": base_items_qs.count(),
        "pending_broken": pending_broken,
        "now": now,
    }
    return render(request, "catalog/distributor_panel.html", ctx)


@login_required
def distributor_calendar(request):
    """Calendario mensual con vencimientos y agenda de los próximos 14 días."""
    redirect_response = _ensure_distributor(request)
    if redirect_response is not None:
        return redirect_response

    import calendar as _calendar
    from datetime import date, timedelta
    from orders.models import OrderItem, Order

    today = timezone.localdate()
    # Soporta ?month=YYYY-MM
    raw_month = (request.GET.get("month") or "").strip()
    try:
        if raw_month:
            yy, mm = raw_month.split("-")
            current = date(int(yy), int(mm), 1)
        else:
            current = today.replace(day=1)
    except (ValueError, TypeError):
        current = today.replace(day=1)

    # mes previo / siguiente
    if current.month == 1:
        prev_month = date(current.year - 1, 12, 1)
    else:
        prev_month = date(current.year, current.month - 1, 1)
    if current.month == 12:
        next_month = date(current.year + 1, 1, 1)
    else:
        next_month = date(current.year, current.month + 1, 1)

    cal = _calendar.Calendar(firstweekday=0)  # lunes
    weeks_dates = cal.monthdatescalendar(current.year, current.month)

    # Cuentas que vencen dentro del mes ± 2 días
    month_start = date(current.year, current.month, 1)
    last_day = _calendar.monthrange(current.year, current.month)[1]
    month_end = date(current.year, current.month, last_day)
    range_start = month_start - timedelta(days=2)
    range_end = month_end + timedelta(days=2)

    items_qs = (
        OrderItem.objects
        .filter(
            order__user=request.user,
            order__status=Order.Status.DELIVERED,
            expires_at__isnull=False,
            expires_at__date__gte=range_start,
            expires_at__date__lte=range_end,
        )
        .select_related("order", "product", "plan")
        .order_by("expires_at")
    )

    # Indexar por fecha
    by_date = {}
    for it in items_qs:
        d = timezone.localtime(it.expires_at).date()
        by_date.setdefault(d, []).append(it)

    # Construir matriz de semanas con metadata
    weeks = []
    for week in weeks_dates:
        row = []
        for d in week:
            items = by_date.get(d, [])
            row.append({
                "date": d,
                "in_month": d.month == current.month,
                "is_today": d == today,
                "is_past": d < today,
                "items": items,
                "count": len(items),
            })
        weeks.append(row)

    # Próximos 14 días en lista (agenda)
    agenda_items = list(
        OrderItem.objects
        .filter(
            order__user=request.user,
            order__status=Order.Status.DELIVERED,
            expires_at__isnull=False,
            expires_at__date__gte=today,
            expires_at__date__lte=today + timedelta(days=14),
        )
        .select_related("order", "product", "plan")
        .order_by("expires_at")[:30]
    )

    # Total del mes mostrado
    month_total = items_qs.filter(
        expires_at__date__gte=month_start, expires_at__date__lte=month_end
    ).count()

    return render(request, "catalog/distributor_calendar.html", {
        "current": current,
        "weeks": weeks,
        "prev_month": prev_month,
        "next_month": next_month,
        "today": today,
        "agenda_items": agenda_items,
        "month_total": month_total,
    })


@login_required
def distributor_support(request):
    """Centro de soporte interno del distribuidor: 3 motivos rápidos + historial."""
    redirect_response = _ensure_distributor(request)
    if redirect_response is not None:
        return redirect_response

    from support.models import Ticket, CodeRequest

    tickets = list(
        Ticket.objects.filter(user=request.user)
        .order_by("-updated_at")[:15]
    )
    code_requests = list(
        CodeRequest.objects.filter(audience=CodeRequest.Audience.DISTRIBUTOR)
        .filter(account_email__iexact=(request.user.email or "_no_email_"))
        .order_by("-created_at")[:5]
    )

    open_count = Ticket.objects.filter(
        user=request.user,
        status__in=[
            Ticket.Status.OPEN,
            Ticket.Status.PENDING_ADMIN,
            Ticket.Status.PENDING_USER,
        ],
    ).count()

    return render(request, "catalog/distributor_support.html", {
        "tickets": tickets,
        "code_requests": code_requests,
        "open_count": open_count,
    })


@login_required
def distributor_accounts(request):
    """Mis cuentas activas: listado completo con credenciales 1-click, búsqueda y filtros."""
    redirect_response = _ensure_distributor(request)
    if redirect_response is not None:
        return redirect_response

    from datetime import timedelta
    from orders.models import OrderItem, Order
    from orders.credentials import parse_profile_pin

    now = timezone.now()
    qs = (
        OrderItem.objects.filter(order__user=request.user, order__status=Order.Status.DELIVERED)
        .select_related("order", "product", "plan")
        .order_by("expires_at", "-order__created_at")
    )

    status_filter = (request.GET.get("status") or "all").strip()
    search_q = (request.GET.get("q") or "").strip()
    platform_filter = (request.GET.get("platform") or "").strip()

    if status_filter == "active":
        qs = qs.filter(expires_at__gt=now)
    elif status_filter == "expiring":
        qs = qs.filter(expires_at__gt=now, expires_at__lte=now + timedelta(days=7))
    elif status_filter == "expired":
        qs = qs.filter(expires_at__lte=now)
    elif status_filter == "broken":
        qs = qs.filter(reported_broken_at__isnull=False)

    if platform_filter:
        qs = qs.filter(product__slug=platform_filter)

    if search_q:
        from django.db.models import Q
        qs = qs.filter(
            Q(product_name__icontains=search_q)
            | Q(plan_name__icontains=search_q)
            | Q(final_customer_name__icontains=search_q)
            | Q(final_customer_whatsapp__icontains=search_q)
            | Q(requested_profile_name__icontains=search_q)
        )

    # Plataformas para el filtro (de los items del distribuidor)
    platforms = (
        OrderItem.objects.filter(order__user=request.user, order__status=Order.Status.DELIVERED)
        .values("product__slug", "product__name", "product__icon")
        .distinct()
        .order_by("product__name")
    )

    # Construir items con credenciales parseadas para mostrar prolijo en cards.
    items = []
    for it in qs[:200]:
        creds_raw = it.delivered_credentials or ""
        profile, pin = parse_profile_pin(creds_raw)
        # parse email/password
        email_val = ""
        password_val = ""
        for ln in creds_raw.splitlines():
            low = ln.lower().strip()
            if not email_val and (
                low.startswith("correo") or low.startswith("email")
                or low.startswith("usuario") or low.startswith("user")
            ):
                if ":" in ln:
                    email_val = ln.split(":", 1)[1].strip()
                elif "=" in ln:
                    email_val = ln.split("=", 1)[1].strip()
            elif not password_val and (
                low.startswith("contraseña") or low.startswith("contrasena")
                or low.startswith("password") or low.startswith("pass")
                or low.startswith("clave")
            ):
                if ":" in ln:
                    password_val = ln.split(":", 1)[1].strip()
                elif "=" in ln:
                    password_val = ln.split("=", 1)[1].strip()
        days_left = None
        if it.expires_at:
            delta = (it.expires_at - now).days
            days_left = delta
        items.append({
            "obj": it,
            "email": email_val,
            "password": password_val,
            "profile": profile or it.requested_profile_name,
            "pin": pin or it.requested_pin,
            "raw": creds_raw,
            "days_left": days_left,
        })

    # Conteos para los chips
    base_counts_qs = OrderItem.objects.filter(
        order__user=request.user, order__status=Order.Status.DELIVERED
    )
    counts = {
        "all": base_counts_qs.count(),
        "active": base_counts_qs.filter(expires_at__gt=now).count(),
        "expiring": base_counts_qs.filter(
            expires_at__gt=now, expires_at__lte=now + timedelta(days=7)
        ).count(),
        "expired": base_counts_qs.filter(expires_at__lte=now).count(),
        "broken": base_counts_qs.filter(reported_broken_at__isnull=False).count(),
    }

    return render(request, "catalog/distributor_accounts.html", {
        "items": items,
        "counts": counts,
        "platforms": platforms,
        "status_filter": status_filter,
        "platform_filter": platform_filter,
        "search_q": search_q,
        "now": now,
    })


@login_required
def distributor_catalog(request):
    """Catálogo con precios mayoristas — solo para distribuidores aprobados."""
    redirect_response = _ensure_distributor(request)
    if redirect_response is not None:
        return redirect_response

    products = list(
        Product.objects.filter(
            is_active=True,
            plans__is_active=True,
            plans__available_for_distributor=True,
        )
        .select_related("category")
        .prefetch_related("plans")
        .distinct()
    )
    # Calcula el copy de WhatsApp por producto para que el template no tenga
    # que importar nada y JS pueda copiarlo de un atributo data-*.
    for product in products:
        product.whatsapp_pitch = product.whatsapp_pitch_for(request.user)
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
            "🔗 https://virtualidadsp.com/panel-virtualidadsp/orders/orderitem/"
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

    site_name = "VirtualidadSP"
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
        getattr(dj_settings, "DEFAULT_FROM_EMAIL", "ventas@virtualidadsp.com"),
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


def platform_landing(request, slug: str):
    """Landing page SEO por plataforma (Netflix, Disney+, etc.)."""
    landing = get_object_or_404(PlatformLanding, slug=slug, is_published=True)

    products = list(
        landing.get_featured_products()
        .select_related("category")
        .prefetch_related("plans")
        .filter(is_active=True)
        [:12]
    )

    # Reseñas de productos relacionados
    product_ids = [p.id for p in products]
    reviews = []
    if product_ids:
        reviews = list(
            ProductReview.objects
            .filter(
                product_id__in=product_ids,
                status=ProductReview.Status.APPROVED,
            )
            .select_related("product")
            .order_by("-created_at")[:6]
        )

    # Otras landings para el footer
    other_landings = PlatformLanding.objects.filter(
        is_published=True
    ).exclude(pk=landing.pk).order_by("order", "name")[:6]

    context = {
        "landing": landing,
        "products": products,
        "reviews": reviews,
        "other_landings": other_landings,
    }
    return render(request, "catalog/platform_landing.html", context)


def _client_ip(request) -> str | None:
    """Best-effort: ip del cliente para auditoria de alertas."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


@require_POST
def back_in_stock_subscribe(request, slug: str):
    """Endpoint para suscribirse a una alerta back-in-stock.

    Acepta application/x-www-form-urlencoded (form normal) y
    devuelve JSON si el cliente envió ``Accept: application/json``,
    si no redirige al detalle del producto con un mensaje flash.
    """
    product = get_object_or_404(
        Product.objects.select_related("category"),
        slug=slug, is_active=True,
    )
    email = (request.POST.get("email") or "").strip().lower()
    plan_id = request.POST.get("plan") or ""
    wants_json = "application/json" in request.headers.get("Accept", "").lower()

    error = ""
    if not email:
        error = "Necesitamos tu correo para avisarte."
    else:
        try:
            validate_email(email)
        except ValidationError:
            error = "Ese correo no parece válido. Revisalo y reintentá."

    plan = None
    if plan_id:
        plan = Plan.objects.filter(pk=plan_id, product=product, is_active=True).first()

    if error:
        if wants_json:
            return JsonResponse({"ok": False, "error": error}, status=400)
        messages.error(request, error)
        return redirect("catalog:product", slug=product.slug)

    # Evita duplicados: si ya hay una alerta pendiente para ese email+producto+plan,
    # no crea otra.
    existing = BackInStockAlert.objects.filter(
        email=email, product=product, plan=plan,
        status=BackInStockAlert.Status.PENDING,
    ).first()
    created = False
    if existing is None:
        BackInStockAlert.objects.create(
            email=email,
            product=product,
            plan=plan,
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:255],
            ip=_client_ip(request),
        )
        created = True

    msg = (
        "¡Listo! Te vamos a avisar a {} apenas vuelva el stock.".format(email)
        if created else
        "Ya tenías una alerta pendiente con ese correo. Te avisaremos al volver el stock."
    )
    if wants_json:
        return JsonResponse({"ok": True, "created": created, "message": msg})
    messages.success(request, msg)
    return redirect("catalog:product", slug=product.slug)

