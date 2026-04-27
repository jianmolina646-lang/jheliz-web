from django.conf import settings

from .models import Category


def site_context(request):
    cart_count = 0
    cart_items = request.session.get("cart") or []
    if isinstance(cart_items, list):
        cart_count = sum(int(it.get("quantity", 0)) for it in cart_items)
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
    }
