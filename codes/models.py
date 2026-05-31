"""Modelos del bot de códigos.

El admin da de alta a cada cliente del bot (``CodeBotClient``) y le asigna
los correos de las cuentas que compró (``AssignedEmail``). El cliente, desde
Telegram, solo puede pedir el código de Netflix de los correos que tiene
asignados; nunca de cuentas ajenas.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class CodeBotClient(models.Model):
    """Un cliente autorizado a usar el bot de códigos.

    Se identifica por su ``telegram_chat_id``. Al hacer ``/start`` por primera
    vez queda creado pero ``is_active=False`` (pendiente); el admin lo activa
    y le asigna correos desde el panel.
    """

    telegram_chat_id = models.CharField(
        "Chat ID de Telegram", max_length=32, unique=True
    )
    telegram_username = models.CharField(
        "Usuario de Telegram", max_length=64, blank=True
    )
    display_name = models.CharField("Nombre", max_length=120, blank=True)
    is_active = models.BooleanField(
        "Activo",
        default=False,
        help_text="Si está desactivado, el bot no le entrega códigos.",
    )
    note = models.CharField("Nota interna", max_length=200, blank=True)
    created_at = models.DateTimeField("Alta", auto_now_add=True)
    last_seen_at = models.DateTimeField("Último uso", null=True, blank=True)

    class Meta:
        verbose_name = "Cliente del bot de códigos"
        verbose_name_plural = "Clientes del bot de códigos"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        label = self.display_name or self.telegram_username or self.telegram_chat_id
        return f"{label} ({self.telegram_chat_id})"

    def touch(self) -> None:
        """Marca el último uso sin disparar señales pesadas."""
        self.last_seen_at = timezone.now()
        self.save(update_fields=["last_seen_at"])


class AssignedEmail(models.Model):
    """Un correo de cuenta que el admin asignó a un cliente.

    Un mismo correo puede estar asignado a varios clientes (cuentas
    compartidas por perfiles), por eso la unicidad es por (cliente, correo).
    """

    client = models.ForeignKey(
        CodeBotClient,
        related_name="emails",
        on_delete=models.CASCADE,
        verbose_name="Cliente",
    )
    email = models.EmailField("Correo de la cuenta")
    note = models.CharField("Nota (plataforma/perfil)", max_length=120, blank=True)
    created_at = models.DateTimeField("Asignado", auto_now_add=True)

    class Meta:
        verbose_name = "Correo asignado"
        verbose_name_plural = "Correos asignados"
        ordering = ("email",)
        constraints = [
            models.UniqueConstraint(
                fields=["client", "email"], name="uniq_client_email"
            )
        ]

    def __str__(self) -> str:
        return f"{self.email} → {self.client_id}"

    def save(self, *args, **kwargs):
        # Normaliza el correo para que el match con la bandeja sea fiable.
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)
