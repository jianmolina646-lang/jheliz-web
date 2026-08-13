from django.conf import settings
import re

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

from services.models import DigitalService

from .crypto import decrypt_secret, encrypt_secret


class DigitalAccount(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Disponible"
        RESERVED = "reserved", "Reservada"
        SOLD = "sold", "Vendida"
        REVIEW = "review", "En revisión"
        BLOCKED = "blocked", "Bloqueada"
        EXPIRED = "expired", "Vencida"
        RETIRED = "retired", "Retirada"

    class BillingMethod(models.TextChoices):
        CARD = "card", "Tarjeta"
        GIFT_CARD = "gift_card", "Gift card o saldo"
        PAYPAL = "paypal", "PayPal"
        OPERATOR = "operator", "Operador"
        OTHER = "other", "Otro"

    service = models.ForeignKey(
        DigitalService,
        on_delete=models.PROTECT,
        related_name="accounts",
        verbose_name="servicio",
    )
    email = models.EmailField("correo", max_length=254)
    encrypted_password = models.TextField(blank=True, editable=False)
    status = models.CharField(
        "estado", max_length=16, choices=Status.choices, default=Status.AVAILABLE, db_index=True
    )
    purchase_date = models.DateField("fecha de compra", null=True, blank=True)
    renewal_date = models.DateField("fecha de renovación", null=True, blank=True, db_index=True)
    acquisition_cost = models.DecimalField(
        "costo de adquisición",
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    billing_method = models.CharField(
        "método de pago",
        max_length=20,
        choices=BillingMethod.choices,
        default=BillingMethod.CARD,
    )
    billing_reference = models.CharField(
        "referencia de pago",
        max_length=32,
        blank=True,
        validators=[RegexValidator(r"^[\w .-]*$", "Usa solo una etiqueta o últimos 4 dígitos.")],
        help_text="Etiqueta segura o últimos 4 dígitos. Nunca guardes el número completo ni CVV.",
    )
    country = models.CharField("país o región", max_length=80, blank=True)
    notes = models.TextField("notas internas", blank=True, max_length=1000)
    last_verified_at = models.DateTimeField("última verificación", null=True, blank=True)
    is_featured = models.BooleanField("destacada", default=False, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="digital_accounts_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("service__name", "email")
        constraints = [
            models.UniqueConstraint(fields=("service", "email"), name="unique_service_email")
        ]
        indexes = [models.Index(fields=("service", "status"), name="inventory_service_status")]
        verbose_name = "cuenta digital"
        verbose_name_plural = "cuentas digitales"

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if len(re.findall(r"\d", self.billing_reference)) > 4:
            raise ValidationError(
                {"billing_reference": "Guarda como máximo los últimos 4 dígitos."}
            )

    def set_password(self, value: str) -> None:
        self.encrypted_password = encrypt_secret(value)

    def get_password(self) -> str:
        return decrypt_secret(self.encrypted_password)

    @property
    def has_password(self) -> bool:
        return bool(self.encrypted_password)

    @property
    def masked_email(self) -> str:
        local, separator, domain = self.email.partition("@")
        if not separator:
            return self.email
        return f"{local[:2]}{'•' * max(3, min(7, len(local) - 2))}@{domain}"

    def __str__(self) -> str:
        return f"{self.service}: {self.email}"
