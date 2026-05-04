"""Signals que disparan publicaciones automáticas al canal de Telegram
y notificaciones de back-in-stock.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import BackInStockAlert, Product, StockItem

logger = logging.getLogger(__name__)

# Marcador en memoria del estado previo de is_active. No requiere migración
# porque sólo necesitamos saber el flip dentro del mismo proceso de admin.
_ACTIVATION_FLAG = "_jheliz_was_active"
# Marcador para detectar el flip de status del StockItem.
_STOCK_PREV_STATUS_FLAG = "_jheliz_prev_status"


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
    if getattr(instance, "telegram_audience", "both") == "none":
        # Admin configuró este producto para no publicarse en Telegram.
        return
    try:
        telegram.announce_product(instance, kind="new")
    except Exception:
        logger.exception("No se pudo publicar el producto %s en el canal", instance.pk)


@receiver(pre_save, sender=StockItem)
def _capture_previous_stock_status(sender, instance: StockItem, **kwargs):
    if not instance.pk:
        setattr(instance, _STOCK_PREV_STATUS_FLAG, None)
        return
    try:
        previous = StockItem.objects.only("status").get(pk=instance.pk)
    except StockItem.DoesNotExist:
        setattr(instance, _STOCK_PREV_STATUS_FLAG, None)
        return
    setattr(instance, _STOCK_PREV_STATUS_FLAG, previous.status)


@receiver(post_save, sender=StockItem)
def _notify_back_in_stock(sender, instance: StockItem, created, **kwargs):
    """Cuando un StockItem queda en estado AVAILABLE, avisa por mail a
    los suscriptores pendientes de ese producto/plan y los marca como
    notificados.

    Casos:
    - Stock recién creado en estado AVAILABLE → notifica.
    - Stock existente que pasa de RESERVED/SOLD/DEFECTIVE/DISABLED a
      AVAILABLE → notifica (ej: una cuenta que volvió a ser válida).
    """
    if instance.status != StockItem.Status.AVAILABLE:
        return
    prev_status = getattr(instance, _STOCK_PREV_STATUS_FLAG, None)
    became_available = created or (
        prev_status is not None
        and prev_status != StockItem.Status.AVAILABLE
    )
    if not became_available:
        return

    from .back_in_stock import notify_pending_alerts

    try:
        notify_pending_alerts(instance.product, instance.plan)
    except Exception:
        logger.exception(
            "No se pudieron enviar alertas back-in-stock para producto=%s plan=%s",
            instance.product_id, instance.plan_id,
        )
