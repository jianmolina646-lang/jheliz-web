from django.conf import settings

from .models import Category


def site_context(request):
    return {
        "SITE_NAME": settings.SITE_NAME,
        "SITE_TAGLINE": settings.SITE_TAGLINE,
        "CURRENCY_SYMBOL": settings.DEFAULT_CURRENCY_SYMBOL,
        "CURRENCY_CODE": settings.DEFAULT_CURRENCY,
        "WHATSAPP_NUMBER": settings.WHATSAPP_NUMBER,
        "TELEGRAM_USERNAME": settings.TELEGRAM_USERNAME,
        "nav_categories": Category.objects.filter(is_active=True)[:12],
    }
