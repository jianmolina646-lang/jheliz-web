from django.conf import settings
from django.core.cache import cache

from .models import Category, PromoBanner, SiteSettings


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

    return {
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
