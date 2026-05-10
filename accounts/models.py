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
    """Proxy para gestionar a los distribuidores (aprobados o pendientes)."""

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


class PushSubscription(models.Model):
    """Suscripción Web Push registrada por un cliente desde su navegador.

    El navegador registra el service worker y obtiene una subscription con
    `endpoint` (URL del push service de Google/Mozilla/etc) + `p256dh` + `auth`
    (claves para cifrar el payload). Esos datos se mandan al backend acá.
    Después el admin puede mandar notificaciones broadcast a todos.
    """

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE,
        null=True, blank=True, related_name="push_subscriptions",
        help_text="Usuario asociado (puede ser null si el cliente nunca se logueó).",
    )
    endpoint = models.URLField("Endpoint del push service", max_length=600, unique=True)
    p256dh = models.CharField("Clave p256dh (Base64URL)", max_length=128)
    auth = models.CharField("Clave auth (Base64URL)", max_length=64)
    user_agent = models.CharField(
        "User-Agent del navegador", max_length=300, blank=True,
        help_text="Para distinguir Chrome desktop / Safari iOS / etc.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(
        "Último error de envío", max_length=200, blank=True,
        help_text="Si la última notificación falló, se guarda el error acá.",
    )
    failed_count = models.PositiveIntegerField(
        "Veces fallidas seguidas", default=0,
        help_text="Cuando llega a 3, se desactiva la subscripción.",
    )
    is_enabled = models.BooleanField("Activa", default=True)

    class Meta:
        verbose_name = "Subscripción push"
        verbose_name_plural = "Subscripciones push"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["is_enabled", "created_at"]),
        ]

    def __str__(self) -> str:
        who = self.user.email if self.user_id else "anónimo"
        return f"PushSub {who} ({self.created_at:%Y-%m-%d})"
