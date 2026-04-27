import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models

from .encryption import EncryptedTextField


class PaymentSettings(models.Model):
    """Singleton con la config de pagos manuales (Yape) editable desde el admin."""

    yape_enabled = models.BooleanField("Yape activo", default=False)
    yape_holder_name = models.CharField(
        "Nombre del titular (Yape)", max_length=120, blank=True,
        help_text="Nombre que aparece al transferir por Yape, ej: Jhonatan Molina.",
    )
    yape_phone = models.CharField(
        "Número Yape", max_length=30, blank=True,
        help_text="Celular asociado a Yape, ej: +51 999 999 999.",
    )
    yape_qr = models.ImageField(
        "QR de Yape", upload_to="payments/yape/", blank=True,
        help_text="Captura o export del QR de tu cuenta Yape.",
    )
    yape_instructions = models.TextField(
        "Instrucciones extra", blank=True,
        help_text="Texto adicional bajo el QR (ej: horario, verificación extra).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración de pagos"
        verbose_name_plural = "Configuración de pagos"

    def __str__(self) -> str:
        return "Configuración de pagos"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "PaymentSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente de pago"
        VERIFYING = "verifying", "Verificando pago"
        PAID = "paid", "Pagado"
        PREPARING = "preparing", "En preparación"
        DELIVERED = "delivered", "Entregado"
        CANCELED = "canceled", "Cancelado"
        FAILED = "failed", "Fallido"
        REFUNDED = "refunded", "Reembolsado"

    class Channel(models.TextChoices):
        WEB = "web", "Web"
        TELEGRAM = "telegram", "Telegram"
        MANUAL = "manual", "Manual"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="orders",
    )
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    telegram_username = models.CharField(max_length=60, blank=True)
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.WEB)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=10, default="PEN")
    payment_provider = models.CharField(max_length=30, blank=True)
    payment_reference = models.CharField(max_length=120, blank=True, db_index=True)
    notes = models.TextField(blank=True)
    payment_proof = models.ImageField(
        "Comprobante de pago", upload_to="payments/proofs/", blank=True,
        help_text="Captura del comprobante Yape subida por el cliente.",
    )
    payment_proof_uploaded_at = models.DateTimeField(null=True, blank=True)
    payment_rejection_reason = models.TextField(
        "Motivo de rechazo", blank=True,
        help_text="Visible para el cliente cuando el comprobante es rechazado.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"

    def __str__(self) -> str:
        return f"Pedido #{self.pk} ({self.get_status_display()})"

    @property
    def short_uuid(self) -> str:
        return str(self.uuid)[:8]

    def recompute_total(self) -> Decimal:
        total = sum((item.unit_price * item.quantity for item in self.items.all()), Decimal("0.00"))
        self.total = total
        self.save(update_fields=["total"])
        return total


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="+",
    )
    plan = models.ForeignKey(
        "catalog.Plan", on_delete=models.PROTECT, related_name="+",
    )
    stock_item = models.ForeignKey(
        "catalog.StockItem", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="order_items",
    )
    product_name = models.CharField(max_length=160)
    plan_name = models.CharField(max_length=120)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    # Datos que el cliente pide (flujo manual)
    requested_profile_name = models.CharField(
        "Nombre del perfil solicitado", max_length=60, blank=True,
    )
    requested_pin = models.CharField(
        "PIN solicitado", max_length=8, blank=True,
        help_text="PIN numérico que el cliente quiere en su perfil.",
    )
    customer_notes = models.TextField(
        "Notas del cliente", blank=True,
        help_text="Preferencias adicionales (idioma, recordatorio de vencimiento, etc).",
    )
    delivered_credentials = EncryptedTextField(blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    # Recordatorios de vencimiento ya enviados (evita duplicados):
    expiry_reminder_3d_sent_at = models.DateTimeField(null=True, blank=True)
    expiry_reminder_1d_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Item de pedido"
        verbose_name_plural = "Items de pedido"
        indexes = [
            models.Index(fields=["expires_at"], name="orderitem_expires_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.product_name} \u2014 {self.plan_name}"

    @property
    def subtotal(self) -> Decimal:
        return self.unit_price * self.quantity
