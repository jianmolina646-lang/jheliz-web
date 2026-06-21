"""Modelos del chat en vivo (cliente <-> admin) integrado al admin VirtualidadSP."""

from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


def _generate_room_token() -> str:
    """Token público (no secreto, pero único) que vive en localStorage del visitante.

    Sirve para que el visitante reabra su sala en visitas posteriores sin
    crear una nueva conversación cada vez.
    """
    return secrets.token_urlsafe(20)


class ChatRoom(models.Model):
    """Una conversación entre un visitante (cliente) y el admin.

    Una sala puede pertenecer a un usuario logueado (``user``) o a un
    visitante anónimo identificado por su email + un ``token`` único
    guardado en localStorage del navegador.
    """

    class Status(models.TextChoices):
        OPEN = "open", "Abierta"
        CLOSED = "closed", "Cerrada"

    token = models.CharField(
        "Token público", max_length=48, unique=True,
        default=_generate_room_token, editable=False,
        help_text="Identificador opaco que vive en el navegador del visitante.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="chat_rooms",
        verbose_name="Usuario (si está logueado)",
    )
    customer_name = models.CharField(
        "Nombre", max_length=80, blank=True, default="",
    )
    customer_email = models.EmailField("Correo", blank=True, default="")
    status = models.CharField(
        "Estado", max_length=10, choices=Status.choices,
        default=Status.OPEN, db_index=True,
    )
    page_url = models.CharField(
        "Página al iniciar", max_length=500, blank=True, default="",
        help_text="URL desde la que se abrió el chat por primera vez.",
    )
    user_agent = models.CharField(max_length=255, blank=True, default="")
    ip = models.GenericIPAddressField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    last_admin_seen_at = models.DateTimeField(null=True, blank=True)
    last_customer_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-last_message_at", "-created_at")
        verbose_name = "Sala de chat"
        verbose_name_plural = "Salas de chat"
        indexes = [
            models.Index(fields=["status", "-last_message_at"]),
            models.Index(fields=["customer_email"]),
        ]

    def __str__(self) -> str:
        who = self.customer_name or self.customer_email or f"anónimo #{self.pk}"
        return f"Chat con {who}"

    @property
    def display_name(self) -> str:
        if self.customer_name:
            return self.customer_name
        if self.customer_email:
            return self.customer_email.split("@")[0]
        if self.user_id and self.user:
            return self.user.get_full_name() or self.user.username
        return f"Visitante #{self.pk}"

    @property
    def admin_unread_count(self) -> int:
        """Cantidad de mensajes del cliente que el admin no ha visto."""
        qs = self.messages.filter(sender=ChatMessage.Sender.CUSTOMER)
        if self.last_admin_seen_at:
            qs = qs.filter(created_at__gt=self.last_admin_seen_at)
        return qs.count()

    @property
    def customer_unread_count(self) -> int:
        """Cantidad de mensajes del admin que el cliente no ha visto."""
        qs = self.messages.filter(sender=ChatMessage.Sender.ADMIN)
        if self.last_customer_seen_at:
            qs = qs.filter(created_at__gt=self.last_customer_seen_at)
        return qs.count()

    def mark_admin_seen(self) -> None:
        self.last_admin_seen_at = timezone.now()
        self.save(update_fields=["last_admin_seen_at"])

    def mark_customer_seen(self) -> None:
        self.last_customer_seen_at = timezone.now()
        self.save(update_fields=["last_customer_seen_at"])

    def touch(self) -> None:
        """Actualiza ``last_message_at`` cuando entra un mensaje nuevo."""
        self.last_message_at = timezone.now()
        if self.status == self.Status.CLOSED:
            self.status = self.Status.OPEN
        self.save(update_fields=["last_message_at", "status"])


class ChatMessage(models.Model):
    """Un mensaje dentro de una sala."""

    class Sender(models.TextChoices):
        CUSTOMER = "customer", "Cliente"
        ADMIN = "admin", "Admin"
        SYSTEM = "system", "Sistema"

    room = models.ForeignKey(
        ChatRoom, on_delete=models.CASCADE, related_name="messages",
    )
    sender = models.CharField(max_length=10, choices=Sender.choices)
    sender_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="chat_messages_sent",
        help_text="Usuario admin que mandó el mensaje, si aplica.",
    )
    body = models.TextField("Mensaje", blank=True, default="")
    image = models.ImageField(
        "Imagen", upload_to="livechat/images/%Y/%m/",
        null=True, blank=True, max_length=500,
        help_text="Imagen adjunta enviada desde el chat.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
        verbose_name = "Mensaje"
        verbose_name_plural = "Mensajes"
        indexes = [
            models.Index(fields=["room", "created_at"]),
        ]

    def __str__(self) -> str:
        snippet = (self.body or "")[:40] or ("📷 imagen" if self.image else "")
        return f"{self.get_sender_display()}: {snippet}"
