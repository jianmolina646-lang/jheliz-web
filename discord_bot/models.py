"""Modelos persistentes para el bot de Discord.

``DiscordOrderThread`` mapea un ``orders.Order`` con su thread en Discord
para que los avisos de cambio de estado (pagado, entregando, entregado,
etc.) se sigan posteando dentro del mismo thread en vez de crear ruido en
el canal principal.
"""

from __future__ import annotations

from django.db import models


class DiscordOrderThread(models.Model):
    """Asocia un pedido con su thread del canal #pedidos-nuevos."""

    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="discord_thread",
    )
    channel_id = models.CharField(max_length=32)
    thread_id = models.CharField(max_length=32, db_index=True)
    root_message_id = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_status_posted = models.CharField(max_length=32, blank=True)

    class Meta:
        verbose_name = "Thread Discord de pedido"
        verbose_name_plural = "Threads Discord de pedidos"

    def __str__(self) -> str:
        return f"Order #{self.order_id} → thread {self.thread_id}"
