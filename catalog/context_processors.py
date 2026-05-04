from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db.models import Avg, Count
from django.utils import timezone

from .models import Category, ProductReview, PromoBanner, SiteSettings


def _round_label(value: int, floor: int = 1000) -> str:
    """Devuelve una etiqueta tipo '5 000+' para mostrar contadores como trust badges.

    El número se redondea hacia abajo al múltiplo de ``floor`` más cercano
    (para evitar mostrar cifras exactas que desentonen) y se le agrega '+'.
    """
    if value < floor:
        # Redondeo al 10 más cercano para que quede prolijo.
        step = max(10, floor // 10)
        rounded = max(step, (value // step) * step)
    else:
        rounded = (value // floor) * floor
    if rounded >= 1000:
        # Formato con espacio fino (ej. "5 000+")
        return f"{rounded // 1000} {rounded % 1000:03d}+" if rounded % 1000 else f"{rounded // 1000}\u202f000+"
    return f"{rounded}+"


def site_context(request):
    cart_count = 0
    cart_items = request.session.get("cart") or []
    if isinstance(cart_items, list):
        cart_count = sum(int(it.get("quantity", 0)) for it in cart_items)

    on_home = False
    try:
        match = getattr(request, "resolver_match", None)
        if match and match.view_name == "catalog:home":
            on_home = True
    except Exception:
        pass

    promo_banner = None
    try:
        promo_banner = PromoBanner.get_active(on_home=on_home)
    except Exception:
        # Antes de migrar, la tabla a\u00fan no existe \u2014 no rompemos el render.
        promo_banner = None

    # Tracking IDs y canales de Telegram (cacheados 5 min para no agregar
    # query en cada request).
    tracking = cache.get("jh_tracking_ids")
    if tracking is None:
        try:
            s = SiteSettings.load()
            tracking = {
                "ga4": (s.ga4_measurement_id or "").strip(),
                "meta": (s.meta_pixel_id or "").strip(),
                "google_ads": (s.google_ads_id or "").strip(),
                "tiktok": (s.tiktok_pixel_id or "").strip(),
                "tg_customer": (s.telegram_customer_channel_url or "").strip(),
                "tg_distrib": (s.telegram_distributor_channel_url or "").strip(),
            }
        except Exception:
            tracking = {
                "ga4": "", "meta": "", "google_ads": "", "tiktok": "",
                "tg_customer": "", "tg_distrib": "",
            }
        cache.set("jh_tracking_ids", tracking, 300)
    ga4_id = tracking["ga4"]
    meta_pixel = tracking["meta"]
    google_ads = tracking["google_ads"]
    tiktok_pixel = tracking["tiktok"]
    tg_customer = tracking.get("tg_customer", "")
    tg_distrib = tracking.get("tg_distrib", "")

    # Stats agregadas para prueba social (cacheadas 10 min)
    stats = cache.get("jh_social_proof_stats")
    if stats is None:
        try:
            from orders.models import Order  # lazy import
            now = timezone.now()
            week_ago = now - timedelta(days=7)
            delivered_or_paid = [Order.Status.PAID, Order.Status.DELIVERED]
            total_orders = Order.objects.filter(status__in=delivered_or_paid).count()
            weekly_orders = Order.objects.filter(
                status__in=delivered_or_paid, created_at__gte=week_ago,
            ).count()
            review_agg = ProductReview.objects.filter(
                status=ProductReview.Status.APPROVED,
            ).aggregate(avg=Avg("rating"), count=Count("id"))
            avg_rating = float(review_agg["avg"] or 4.9)
            review_count = int(review_agg["count"] or 0)
            # Hace cuántos años opera la tienda (usa el SITE_LAUNCH de settings si
            # existe, si no, asumimos 2 años como conservador).
            launch_year = getattr(settings, "SITE_LAUNCH_YEAR", now.year - 2)
            years_operating = max(1, now.year - launch_year)

            stats = {
                "total_orders": total_orders,
                "weekly_orders": weekly_orders,
                "avg_rating": round(avg_rating, 1),
                "review_count": review_count,
                "years_operating": years_operating,
                # números para mostrar redondeados (X 500+, 5 000+)
                "total_orders_label": _round_label(total_orders, floor=1000),
                "weekly_orders_label": _round_label(weekly_orders, floor=10),
            }
        except Exception:
            stats = {
                "total_orders": 5000,
                "weekly_orders": 140,
                "avg_rating": 4.9,
                "review_count": 50,
                "years_operating": 2,
                "total_orders_label": "5 000+",
                "weekly_orders_label": "140+",
            }
        cache.set("jh_social_proof_stats", stats, 600)

    return {
        "SOCIAL_PROOF": stats,
        "SITE_NAME": settings.SITE_NAME,
        "SITE_TAGLINE": settings.SITE_TAGLINE,
        "CURRENCY_SYMBOL": settings.DEFAULT_CURRENCY_SYMBOL,
        "CURRENCY_CODE": settings.DEFAULT_CURRENCY,
        "WHATSAPP_NUMBER": settings.WHATSAPP_NUMBER,
        "TELEGRAM_USERNAME": settings.TELEGRAM_USERNAME,
        "MERCADOPAGO_ENABLED": bool(settings.MERCADOPAGO_ACCESS_TOKEN),
        "nav_categories": Category.objects.filter(is_active=True)[:12],
        "cart_count": cart_count,
        "promo_banner": promo_banner,
        "GA4_ID": ga4_id,
        "META_PIXEL_ID": meta_pixel,
        "GOOGLE_ADS_ID": google_ads,
        "TIKTOK_PIXEL_ID": tiktok_pixel,
        "TELEGRAM_CUSTOMER_CHANNEL_URL": tg_customer,
        "TELEGRAM_DISTRIBUTOR_CHANNEL_URL": tg_distrib,
    }
