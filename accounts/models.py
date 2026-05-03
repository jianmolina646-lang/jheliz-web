from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    CLIENTE = "cliente", "Cliente"
    DISTRIBUIDOR = "distribuidor", "Distribuidor"
    ADMIN = "admin", "Administrador"


class User(AbstractUser):
    """Usuario con roles. Los distribuidores ven precios mayoristas."""

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CLIENTE,
    )
    phone = models.CharField("Tel\u00e9fono / WhatsApp", max_length=30, blank=True)
    telegram_username = models.CharField(
        "Usuario de Telegram", max_length=60, blank=True,
        help_text="Opcional, con o sin @",
    )
    wallet_balance = models.DecimalField(
        "Saldo (S/)", max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    distributor_approved = models.BooleanField(
        "Distribuidor aprobado", default=False,
        help_text="Solo los distribuidores aprobados ven precios mayoristas.",
    )
    admin_notes = models.TextField(
        "Notas internas (admin)", blank=True,
        help_text="Visible sólo para ti. Ej: 'renueva siempre el 5', 'pide recordatorio', 'cliente VIP'.",
    )

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self) -> str:
        return self.get_full_name() or self.username

    @property
    def is_distributor(self) -> bool:
        return self.role == Role.DISTRIBUIDOR and self.distributor_approved

    @property
    def is_customer(self) -> bool:
        return self.role == Role.CLIENTE

    def clean_telegram(self) -> str:
        return self.telegram_username.lstrip("@") if self.telegram_username else ""


class Customer(User):
    """Proxy para mostrar a los clientes en una sección propia del admin."""

    class Meta:
        proxy = True
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"


class Distributor(User):
    """Proxy para mostrar a los distribuidores en una sección propia del admin."""

    class Meta:
        proxy = True
        verbose_name = "Distribuidor"
        verbose_name_plural = "Distribuidores"


class WalletTransaction(models.Model):
    class Kind(models.TextChoices):
        RECARGA = "recarga", "Recarga"
        COMPRA = "compra", "Compra"
        REEMBOLSO = "reembolso", "Reembolso"
        AJUSTE = "ajuste", "Ajuste manual"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="wallet_transactions"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Movimiento de saldo"
        verbose_name_plural = "Movimientos de saldo"

    def __str__(self) -> str:
        return f"{self.user} {self.get_kind_display()} {self.amount}"
