import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


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

    @property
    def is_closed(self) -> bool:
        return self.status in {self.Status.RESOLVED, self.Status.CLOSED}


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


def _gen_token() -> str:
    """Token público (URL-safe) para seguir el estado de una solicitud."""
    return secrets.token_urlsafe(16)


class CodeRequest(models.Model):
    """Solicitud de código (login / activación / hogar) por parte de un
    cliente o distribuidor.

    Flujo manual: el cliente crea la solicitud desde la web, el admin la ve en
    el panel de admin, pega el código que recibió en su buzón personal y al
    guardar la solicitud queda ``DELIVERED``. La página pública de la solicitud
    hace polling y muestra el código al instante.
    """

    class Platform(models.TextChoices):
        NETFLIX = "netflix", "Netflix"
        DISNEY = "disney", "Disney+"
        PRIME = "prime", "Amazon Prime Video"
        MAX = "max", "Max / HBO"
        SPOTIFY = "spotify", "Spotify"
        CRUNCHYROLL = "crunchyroll", "Crunchyroll"
        APPLE = "apple", "Apple TV+"
        VIX = "vix", "ViX"
        PARAMOUNT = "paramount", "Paramount+"
        YOUTUBE = "youtube", "YouTube Premium"
        OTHER = "other", "Otra"

    class CodeType(models.TextChoices):
        LOGIN = "login", "Inicio de sesión"
        DEVICE = "device", "Activación de dispositivo / TV"
        HOME = "home", "Hogar / Estoy de viaje"
        RESET_LINK = "reset_link", "Link de restablecer contraseña"
        OTHER = "other", "Otro"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        DELIVERED = "delivered", "Entregado"
        REJECTED = "rejected", "Rechazado"
        EXPIRED = "expired", "Expirado"

    class Audience(models.TextChoices):
        CUSTOMER = "customer", "Cliente final"
        DISTRIBUTOR = "distributor", "Distribuidor"

    audience = models.CharField(
        max_length=20, choices=Audience.choices,
        default=Audience.CUSTOMER, db_index=True,
    )
    platform = models.CharField(max_length=20, choices=Platform.choices)
    account_email = models.EmailField(
        "Email de la cuenta",
        help_text="Email con el que el cliente inicia sesión en la plataforma.",
    )
    contact_email = models.EmailField(
        "Tu email de contacto", blank=True,
        help_text="Opcional. Para que te avisemos si el código cambia.",
    )
    order_number = models.CharField("N° de pedido", max_length=40, blank=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="code_requests",
        help_text="Si el cliente/distribuidor estaba logueado al solicitar.",
    )
    order = models.ForeignKey(
        "orders.Order", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="code_requests",
        help_text="Pedido asociado si se pudo resolver por order_number.",
    )

    status = models.CharField(
        max_length=20, choices=Status.choices,
        default=Status.PENDING, db_index=True,
    )
    code = models.CharField("Código", max_length=64, blank=True)
    code_type = models.CharField(
        "Tipo de código", max_length=20, choices=CodeType.choices, blank=True,
    )
    admin_note = models.CharField(
        "Nota para el cliente", max_length=200, blank=True,
        help_text="Texto opcional que verá el cliente junto al código.",
    )
    reject_reason = models.CharField(
        "Motivo de rechazo", max_length=200, blank=True,
    )

    token = models.CharField(
        max_length=32, unique=True, db_index=True, default=_gen_token,
        editable=False,
        help_text="Identificador público para consultar el estado desde la web.",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True, editable=False)
    user_agent = models.CharField(max_length=255, blank=True, editable=False)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    responded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        editable=False,
    )

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Solicitud de código"
        verbose_name_plural = "Solicitudes de código"

    def __str__(self) -> str:
        return f"#{self.pk} {self.account_email} ({self.get_platform_display()})"

    def mark_delivered(self, by_user=None) -> None:
        self.status = self.Status.DELIVERED
        self.responded_at = timezone.now()
        if by_user is not None:
            self.responded_by = by_user
        self.save(update_fields=[
            "status", "responded_at", "responded_by",
            "code", "code_type", "admin_note",
        ])

    def mark_rejected(self, reason: str = "", by_user=None) -> None:
        self.status = self.Status.REJECTED
        self.reject_reason = reason[:200]
        self.responded_at = timezone.now()
        if by_user is not None:
            self.responded_by = by_user
        self.save(update_fields=[
            "status", "reject_reason", "responded_at", "responded_by",
        ])

    @property
    def is_pending(self) -> bool:
        return self.status == self.Status.PENDING

    @property
    def is_delivered(self) -> bool:
        return self.status == self.Status.DELIVERED
