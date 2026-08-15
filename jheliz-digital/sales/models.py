import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone

from inventory.models import DigitalAccount


class Sale(models.Model):
    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Efectivo"
        YAPE = "yape", "Yape"
        PLIN = "plin", "Plin"
        TRANSFER = "transfer", "Transferencia"
        CARD = "card", "Tarjeta"
        OTHER = "other", "Otro"

    account = models.OneToOneField(
        DigitalAccount,
        on_delete=models.PROTECT,
        related_name="sale",
        verbose_name="cuenta vendida",
    )
    amount = models.DecimalField(
        "importe de venta",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    payment_method = models.CharField(
        "método de cobro", max_length=16, choices=PaymentMethod.choices
    )
    payment_reference = models.CharField(
        "referencia de cobro",
        max_length=40,
        blank=True,
        validators=[RegexValidator(r"^[\w .-]*$", "Usa solo letras, números, espacios, punto o guion.")],
        help_text="Código de operación o etiqueta segura. Para tarjetas, solo últimos 4 dígitos.",
    )
    sold_at = models.DateTimeField("fecha de venta", default=timezone.now, db_index=True)
    notes = models.TextField("notas internas", blank=True, max_length=500)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sales_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-sold_at", "-pk")
        verbose_name = "venta"
        verbose_name_plural = "ventas"

    def clean(self):
        super().clean()
        if self.payment_method == self.PaymentMethod.CARD:
            digits = re.findall(r"\d", self.payment_reference)
            if len(digits) > 4:
                raise ValidationError(
                    {"payment_reference": "Para tarjetas guarda como máximo los últimos 4 dígitos."}
                )

    def __str__(self):
        return f"{self.account} - {self.amount}"
