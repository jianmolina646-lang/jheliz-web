import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

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


class Coupon(models.Model):
    """Código de descuento que el cliente puede aplicar en el carrito."""

    class DiscountType(models.TextChoices):
        PERCENT = "percent", "Porcentaje (%)"
        FIXED = "fixed", "Monto fijo (S/)"

    class Audience(models.TextChoices):
        ALL = "all", "Todos"
        CUSTOMER = "customer", "Solo cliente final"
        DISTRIBUTOR = "distributor", "Solo distribuidor"

    code = models.CharField(
        "Código", max_length=40, unique=True, db_index=True,
        help_text="Código que el cliente escribe en el carrito (ej. NAVIDAD15). Mayúsculas.",
    )
    description = models.CharField(
        "Descripción interna", max_length=160, blank=True,
        help_text="Solo visible para el admin, ej: 'Campaña Black Friday 2026'.",
    )
    discount_type = models.CharField(
        "Tipo de descuento", max_length=10,
        choices=DiscountType.choices, default=DiscountType.PERCENT,
    )
    discount_value = models.DecimalField(
        "Valor del descuento", max_digits=10, decimal_places=2,
        help_text="Si es porcentaje, número de 1 a 100. Si es monto fijo, soles.",
    )
    is_active = models.BooleanField("Activo", default=True)
    valid_from = models.DateTimeField("Válido desde", null=True, blank=True)
    valid_until = models.DateTimeField("Válido hasta", null=True, blank=True)
    max_uses = models.PositiveIntegerField(
        "Máximo de usos totales", null=True, blank=True,
        help_text="Vacío = sin límite. Cuando se alcanza, el cupón deja de aplicar.",
    )
    max_uses_per_user = models.PositiveIntegerField(
        "Máximo por cliente", default=1,
        help_text="Cuántas veces puede usarlo un mismo cliente. 0 = sin límite.",
    )
    times_used = models.PositiveIntegerField("Usos actuales", default=0, editable=False)
    min_order_total = models.DecimalField(
        "Total mínimo del pedido (S/)", max_digits=10, decimal_places=2,
        default=Decimal("0.00"),
        help_text="0 = sin mínimo. Si el total del carrito es menor, el cupón no aplica.",
    )
    audience = models.CharField(
        "Aplica para", max_length=20, choices=Audience.choices, default=Audience.ALL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cupón"
        verbose_name_plural = "Cupones"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.code} ({self.discount_label})"

    @property
    def discount_label(self) -> str:
        if self.discount_type == self.DiscountType.PERCENT:
            return f"{self.discount_value:g}% off"
        return f"S/ {self.discount_value:g} off"

    def clean(self):
        if self.discount_type == self.DiscountType.PERCENT:
            if not (0 < self.discount_value <= 100):
                raise ValidationError({"discount_value": "Para porcentaje usa 1-100."})

    def save(self, *args, **kwargs):
        # Normaliza el código: mayúsculas + sin espacios.
        if self.code:
            self.code = self.code.upper().strip().replace(" ", "")
        super().save(*args, **kwargs)

    # ---- Lógica de validación / cálculo --------------------------------------

    def is_currently_valid(self) -> bool:
        """¿Está el cupón en su ventana temporal y bajo cap global?"""
        if not self.is_active:
            return False
        now = timezone.now()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        if self.max_uses is not None and self.times_used >= self.max_uses:
            return False
        return True

    def is_eligible_for(self, user, subtotal: Decimal) -> tuple[bool, str]:
        """Returns (ok, error_message). Mensaje vacío si ok."""
        if not self.is_currently_valid():
            return False, "Este cupón no está disponible ahora mismo."
        if subtotal < self.min_order_total:
            return False, f"Tu carrito debe ser mínimo S/ {self.min_order_total:g} para usar este cupón."
        # Audiencia
        if self.audience != self.Audience.ALL and user is not None and user.is_authenticated:
            role = getattr(user, "role", "")
            if self.audience == self.Audience.CUSTOMER and role != "cliente":
                return False, "Este cupón es solo para clientes finales."
            if self.audience == self.Audience.DISTRIBUTOR and not getattr(user, "distributor_approved", False):
                return False, "Este cupón es solo para distribuidores aprobados."
        # Cap por usuario
        if self.max_uses_per_user and user is not None and user.is_authenticated:
            used_by_user = self.orders.filter(user=user).count()
            if used_by_user >= self.max_uses_per_user:
                return False, "Ya usaste este cupón el máximo de veces permitido."
        return True, ""

    def compute_discount(self, subtotal: Decimal) -> Decimal:
        """Calcula el monto de descuento a aplicar al subtotal dado."""
        if self.discount_type == self.DiscountType.PERCENT:
            discount = (subtotal * self.discount_value / Decimal("100")).quantize(Decimal("0.01"))
        else:
            discount = self.discount_value
        # No descontar más que el subtotal.
        if discount > subtotal:
            discount = subtotal
        return discount


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
    coupon = models.ForeignKey(
        "Coupon", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="orders",
    )
    coupon_code = models.CharField(
        "Código aplicado", max_length=40, blank=True,
        help_text="Snapshot del código por si el cupón se borra después.",
    )
    discount_amount = models.DecimalField(
        "Descuento aplicado", max_digits=10, decimal_places=2,
        default=Decimal("0.00"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"
        indexes = [
            # Filtro más común en el admin: lista por status + ordenado por fecha.
            models.Index(fields=["status", "-created_at"], name="order_status_created_idx"),
            # Filtro por fecha (dashboard, ventas del día/mes, recordatorios).
            models.Index(fields=["-created_at"], name="order_created_idx"),
            # Búsqueda directa por correo y por teléfono desde el admin.
            models.Index(fields=["email"], name="order_email_idx"),
            models.Index(fields=["phone"], name="order_phone_idx"),
            # Métricas por usuario (clientes nuevos vs recurrentes en dashboard).
            models.Index(fields=["user", "status"], name="order_user_status_idx"),
        ]

    def __str__(self) -> str:
        return f"Pedido #{self.pk} ({self.get_status_display()})"

    @property
    def short_uuid(self) -> str:
        return str(self.uuid)[:8]

    @property
    def subtotal(self) -> Decimal:
        return sum(
            (item.unit_price * item.quantity for item in self.items.all()),
            Decimal("0.00"),
        )

    def recompute_total(self) -> Decimal:
        subtotal = self.subtotal
        # Si hay cupón ya asociado pero el descuento no se calculó aún, calcúlalo.
        if self.coupon_id and self.discount_amount == 0:
            self.discount_amount = self.coupon.compute_discount(subtotal)
        total = subtotal - (self.discount_amount or Decimal("0.00"))
        if total < 0:
            total = Decimal("0.00")
        self.total = total
        self.save(update_fields=["total", "discount_amount"])
        return total


class DistributorOrder(Order):
    """Pedido cuyo cliente es distribuidor aprobado."""

    class Meta:
        proxy = True
        verbose_name = "Pedido mayorista"
        verbose_name_plural = "Pedidos mayoristas"


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
