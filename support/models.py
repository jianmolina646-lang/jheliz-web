from django.conf import settings
from django.db import models


class Ticket(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Abierto"
        PENDING_USER = "pending_user", "Esperando al cliente"
        PENDING_ADMIN = "pending_admin", "Esperando al soporte"
        RESOLVED = "resolved", "Resuelto"
        CLOSED = "closed", "Cerrado"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tickets",
    )
    order = models.ForeignKey(
        "orders.Order", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tickets",
    )
    subject = models.CharField("Asunto", max_length=160)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)
        verbose_name = "Ticket"
        verbose_name_plural = "Tickets"

    def __str__(self) -> str:
        return f"#{self.pk} {self.subject}"


class TicketMessage(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="ticket_messages",
    )
    body = models.TextField()
    is_from_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)


class ReplyTemplate(models.Model):
    """Plantilla de respuesta rápida para tickets de soporte.

    El admin puede tener N plantillas (ej. instrucciones para activar Office,
    cómo cambiar la contraseña, qué hacer con error de Netflix) y reutilizarlas
    desde la vista del ticket con un selector.
    """

    class Category(models.TextChoices):
        NETFLIX = "netflix", "Netflix"
        DISNEY = "disney", "Disney+"
        SPOTIFY = "spotify", "Spotify"
        OFFICE = "office", "Office / Microsoft"
        WINDOWS = "windows", "Windows"
        ADOBE = "adobe", "Adobe"
        GENERAL = "general", "General"
        REFUND = "refund", "Reembolso / garantía"
        ACCOUNT = "account", "Activación / acceso"

    name = models.CharField(
        "Nombre", max_length=120,
        help_text="Identificador interno, ej: 'Cómo activar Office 2021'.",
    )
    category = models.CharField(
        "Categoría", max_length=20, choices=Category.choices,
        default=Category.GENERAL, db_index=True,
    )
    subject = models.CharField(
        "Asunto sugerido", max_length=160, blank=True,
        help_text="Si la plantilla se usa al iniciar un ticket o email.",
    )
    body = models.TextField(
        "Cuerpo del mensaje",
        help_text=(
            "Texto que se inserta. Puedes usar {nombre}, {pedido}, {producto}, "
            "{telefono}, {fecha} como variables."
        ),
    )
    is_active = models.BooleanField("Activa", default=True)
    use_count = models.PositiveIntegerField("Veces usada", default=0, editable=False)
    last_used_at = models.DateTimeField("Última vez usada", null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("category", "name")
        verbose_name = "Plantilla de respuesta"
        verbose_name_plural = "Plantillas de respuesta"

    def __str__(self) -> str:
        return f"[{self.get_category_display()}] {self.name}"

    def render(self, *, ticket=None, order=None) -> str:
        """Reemplaza variables en el body usando datos del ticket/pedido."""
        from django.utils import timezone as _tz

        ctx = {
            "nombre": "",
            "pedido": "",
            "producto": "",
            "telefono": "",
            "fecha": _tz.localdate().strftime("%d/%m/%Y"),
        }
        if ticket and ticket.user:
            ctx["nombre"] = ticket.user.get_full_name() or ticket.user.username or ""
        if order is None and ticket is not None:
            order = ticket.order
        if order:
            ctx["pedido"] = order.short_uuid if hasattr(order, "short_uuid") else str(order.pk)
            ctx["telefono"] = getattr(order, "phone", "") or ""
            first_item = order.items.first() if hasattr(order, "items") else None
            if first_item:
                ctx["producto"] = getattr(first_item, "product_name", "") or ""
        try:
            return self.body.format(**ctx)
        except (KeyError, IndexError):
            return self.body
