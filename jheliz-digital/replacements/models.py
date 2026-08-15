from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from inventory.models import DigitalAccount


class Replacement(models.Model):
    class Reason(models.TextChoices):
        ACCESS = "access", "Problema de acceso"
        BLOCKED = "blocked", "Cuenta bloqueada"
        SERVICE = "service", "Falla del servicio"
        EXPIRED = "expired", "Cuenta vencida"
        OTHER = "other", "Otro"

    original_account = models.OneToOneField(
        DigitalAccount,
        on_delete=models.PROTECT,
        related_name="replacement_outgoing",
        verbose_name="cuenta anterior",
    )
    replacement_account = models.OneToOneField(
        DigitalAccount,
        on_delete=models.PROTECT,
        related_name="replacement_incoming",
        verbose_name="cuenta de reposición",
    )
    reason = models.CharField("motivo", max_length=16, choices=Reason.choices)
    replaced_at = models.DateTimeField("fecha de reposición", default=timezone.now, db_index=True)
    notes = models.TextField("notas internas", blank=True, max_length=500)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="replacements_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-replaced_at", "-pk")
        verbose_name = "reposición"
        verbose_name_plural = "reposiciones"

    def clean(self):
        super().clean()
        if not self.original_account_id or not self.replacement_account_id:
            return
        if self.original_account_id == self.replacement_account_id:
            raise ValidationError(
                {"replacement_account": "La cuenta de reposición debe ser diferente."}
            )
        if self.original_account.service_id != self.replacement_account.service_id:
            raise ValidationError(
                {"replacement_account": "La reposición debe pertenecer al mismo servicio."}
            )

    def __str__(self):
        return f"{self.original_account} → {self.replacement_account}"
