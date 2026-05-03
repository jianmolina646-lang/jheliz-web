"""Signals que disparan publicaciones automáticas al canal de Telegram."""

from __future__ import annotations

import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Product

logger = logging.getLogger(__name__)

# Marcador en memoria del estado previo de is_active. No requiere migración
# porque sólo necesitamos saber el flip dentro del mismo proceso de admin.
_ACTIVATION_FLAG = "_jheliz_was_active"


@receiver(pre_save, sender=Product)
def _capture_previous_is_active(sender, instance: Product, **kwargs):
    if not instance.pk:
        setattr(instance, _ACTIVATION_FLAG, False)
        return
    try:
        previous = Product.objects.only("is_active").get(pk=instance.pk)
    except Product.DoesNotExist:
        setattr(instance, _ACTIVATION_FLAG, False)
        return
    setattr(instance, _ACTIVATION_FLAG, previous.is_active)


@receiver(post_save, sender=Product)
def _announce_new_or_activated_product(sender, instance: Product, created, **kwargs):
    """Publica al canal cuando un producto se activa por primera vez.

    Casos:
    - Creado activo → anuncio "Nuevo".
    - Existente, pasa de inactivo a activo → anuncio "Nuevo".
    - Toggle false→true→false→true: cada vez que se prende, anuncia (la
      decisión se toma en el admin; si querés evitarlo, dejalo activo o
      apagá `TELEGRAM_CHANNEL_ID`).
    """
    from orders import telegram

    if not telegram.channel_is_configured():
        return
    was_active = getattr(instance, _ACTIVATION_FLAG, False)
    became_active = (created and instance.is_active) or (not was_active and instance.is_active)
    if not became_active:
        return
    try:
        telegram.announce_product(instance, kind="new")
    except Exception:
        logger.exception("No se pudo publicar el producto %s en el canal", instance.pk)
