"""Modelos de **Jheliz Control** — módulo de gestión de suscripciones para revendedor.

Es un módulo NUEVO e independiente del "Control de cuentas / stock" de la tienda
(ese sigue intacto). Acá el admin lleva su propio cuaderno de revendedor: sus
servicios, sus clientes, las suscripciones que les vendió (con vencimiento,
costo/inversión/utilidad) y un libro simple de ingresos/egresos.

Diseño pensado para la estética "Jheliz Control" (verde esmeralda, tarjetas
blancas, semáforo de vencimiento).
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
import uuid

from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.db.models.functions import Lower
from django.utils import timezone

from config.private_storage import private_media_storage

from config.date_utils import add_service_duration
from orders.encryption import EncryptedTextField
from .currencies import CURRENCY_CHOICES, normalize_currency


class TelegramSentMessage(models.Model):
    """Referencia mínima para administrar mensajes enviados por nuestros bots."""

    bot_key = models.CharField(max_length=32, db_index=True)
    chat_id = models.CharField(max_length=64)
    message_id = models.BigIntegerField()
    sent_at = models.DateTimeField(auto_now_add=True, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("bot_key", "chat_id", "message_id"),
                name="uniq_telegram_sent_message",
            ),
        ]
        ordering = ("-sent_at",)


def renewal_link_expiry():
    return timezone.now() + timedelta(days=45)


class ServiceCategory(models.Model):
    """Categoría de servicios (TV y Cine, Música, Diseño y Educación, VPN…)."""

    name = models.CharField("Nombre", max_length=80, unique=True)
    slug = models.SlugField("Slug", max_length=90, unique=True)
    icon = models.CharField(
        "Icono (Material Symbols)",
        max_length=60,
        default="apps",
        help_text="Nombre del icono de Material Symbols (ej. 'movie', 'music_note').",
    )
    order = models.PositiveIntegerField("Orden", default=0)

    class Meta:
        verbose_name = "Categoría de servicio"
        verbose_name_plural = "Categorías de servicio"
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name


class Service(models.Model):
    """Un servicio que el revendedor ofrece (Netflix, Disney+, Spotify, Canva…)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="jc_services",
        verbose_name="Dueño (inquilino)",
        null=True,
        blank=True,
    )
    name = models.CharField("Nombre", max_length=80)
    category = models.ForeignKey(
        ServiceCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="services",
        verbose_name="Categoría",
    )
    image = models.ImageField(
        "Imagen", upload_to="jheliz_control/servicios/", blank=True, null=True
    )
    icon = models.CharField(
        "Icono (Material Symbols)",
        max_length=60,
        blank=True,
        help_text="Icono de respaldo si no hay imagen (ej. 'live_tv').",
    )
    color = models.CharField(
        "Color", max_length=20, default="#10b981",
        help_text="Color de acento de la tarjeta (hex).",
    )
    is_active = models.BooleanField("Activo", default=True)
    created_at = models.DateTimeField("Creado", auto_now_add=True)

    class Meta:
        verbose_name = "Servicio"
        verbose_name_plural = "Servicios"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"), "owner", name="uniq_service_owner_name_ci"
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def active_subscriptions(self):
        return self.subscriptions.filter(is_archived=False)


class Client(models.Model):
    """Un cliente del revendedor (a quién le vende las suscripciones)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="jc_clients",
        verbose_name="Dueño (inquilino)",
        null=True,
        blank=True,
    )
    name = models.CharField("Nombre", max_length=120)
    telegram = models.CharField(
        "Telegram (@usuario)", max_length=80, blank=True,
        help_text="Con o sin @; se normaliza al guardar.",
    )
    whatsapp = models.CharField(
        "WhatsApp", max_length=40, blank=True,
        help_text="Número con código de país (ej. +51987654321).",
    )
    whatsapp_opt_in_at = models.DateTimeField(
        "Autorizacion para avisos por WhatsApp", null=True, blank=True,
        help_text="Fecha en que el cliente acepto recibir recordatorios.",
    )
    email = models.EmailField("Correo", blank=True)
    notes = models.TextField("Notas", blank=True)
    created_at = models.DateTimeField("Creado", auto_now_add=True)

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        # Normalizamos el handle de Telegram a "@usuario".
        tg = (self.telegram or "").strip()
        if tg and not tg.startswith("@"):
            tg = "@" + tg.lstrip("@")
        self.telegram = tg
        super().save(*args, **kwargs)

    @property
    def telegram_handle(self) -> str:
        """Devuelve el handle sin @ para armar el link t.me/."""
        return (self.telegram or "").lstrip("@")

    @property
    def whatsapp_digits(self) -> str:
        import re
        return re.sub(r"\D", "", self.whatsapp or "")

    @property
    def active_subscriptions(self):
        return self.subscriptions.filter(is_archived=False)


class Subscription(models.Model):
    """Una suscripción vendida a un cliente para un servicio puntual."""

    class Plan(models.TextChoices):
        COMPLETA = "completa", "Cuenta completa"
        PERFIL = "perfil", "Perfil individual"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="jc_subscriptions",
        verbose_name="Dueño (inquilino)",
        null=True,
        blank=True,
    )
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="subscriptions",
        verbose_name="Cliente",
    )
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="subscriptions",
        verbose_name="Servicio",
    )
    account_email = models.CharField("Correo / usuario de la cuenta", max_length=160)
    account_password = EncryptedTextField("Contraseña", blank=True)
    plan = models.CharField(
        "Plan", max_length=12, choices=Plan.choices, default=Plan.PERFIL
    )
    profiles = models.PositiveSmallIntegerField(
        "Perfiles", default=1,
        help_text="Cantidad de perfiles (1 a 7). En cuenta completa, 1.",
    )
    profile_name = models.CharField("Nombre de perfil", max_length=80, blank=True)
    profile_pin = EncryptedTextField("PIN", blank=True)
    plan_label = models.CharField(
        "Plan de suscripción", max_length=40, blank=True,
        help_text="Nombre del plan (ej. Premium, Básico).",
    )

    # Finanzas (USD por defecto; la divisa se guarda por si se cambia a futuro).
    currency = models.CharField("Moneda", max_length=8, choices=CURRENCY_CHOICES, default="PEN")
    exchange_rate = models.DecimalField(
        "Tipo de cambio a moneda principal", max_digits=18, decimal_places=8,
        default=Decimal("1"),
    )
    cost = models.DecimalField(
        "Costo (venta al cliente)", max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    investment = models.DecimalField(
        "Inversión (costo de adquisición)", max_digits=10, decimal_places=2,
        default=Decimal("0.00"),
    )

    starts_at = models.DateTimeField("Inicio", default=timezone.now)
    expires_at = models.DateTimeField("Vence")

    is_archived = models.BooleanField("Archivada", default=False)
    created_at = models.DateTimeField("Creado", auto_now_add=True)
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Suscripción"
        verbose_name_plural = "Suscripciones"
        ordering = ["expires_at"]
        indexes = [
            models.Index(fields=["owner", "is_archived", "expires_at"], name="sub_owner_active_exp_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(profiles__gte=1, profiles__lte=7), name="subscription_profiles_1_7"),
            models.CheckConstraint(condition=models.Q(exchange_rate__gt=0), name="subscription_exchange_rate_gt_0"),
            models.CheckConstraint(condition=models.Q(cost__gte=0, investment__gte=0), name="subscription_amounts_nonnegative"),
        ]

    def __str__(self) -> str:
        return f"{self.service} · {self.client} ({self.account_email})"

    # ── Finanzas ────────────────────────────────────────────────────────
    @property
    def profit(self) -> Decimal:
        """Utilidad = costo (venta) − inversión (adquisición)."""
        return (self.cost or Decimal("0.00")) - (self.investment or Decimal("0.00"))

    # ── Vencimiento ─────────────────────────────────────────────────────
    @property
    def seconds_left(self) -> int:
        if not self.expires_at:
            return 0
        return int((self.expires_at - timezone.now()).total_seconds())

    @property
    def is_expired(self) -> bool:
        return self.seconds_left <= 0

    @property
    def status_color(self) -> str:
        """Semáforo: verde (>3d) · amarillo (24h–3d) · rojo (<24h o vencida)."""
        secs = self.seconds_left
        if secs <= 0:
            return "expired"
        if secs < 24 * 3600:
            return "red"
        if secs <= 3 * 24 * 3600:
            return "yellow"
        return "green"

    @property
    def expires_ts(self) -> int:
        """Timestamp UNIX (segundos) para el contador en vivo del front."""
        if not self.expires_at:
            return 0
        return int(self.expires_at.timestamp())

    @property
    def time_left_label(self) -> str:
        """Etiqueta legible 'Xd Yh Zm' (o 'Vencida')."""
        secs = self.seconds_left
        if secs <= 0:
            return "Vencida"
        days, rem = divmod(secs, 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours or days:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        return " ".join(parts)

    def renew(self, days: int = 30) -> None:
        """Suma la duración desde el vencimiento y conserva el ciclo original."""
        base = self.expires_at or timezone.now()
        self.expires_at = add_service_duration(base, int(days))
        self.save(update_fields=["expires_at", "updated_at"])


class StockEmail(models.Model):
    """Correo de una cuenta en stock (Netflix, Prime…) con su disponibilidad.

    Inventario simple por plataforma: el revendedor carga los correos que
    tiene de cada servicio y marca cuáles siguen disponibles para vender y
    cuáles ya están vendidos/ocupados.
    """

    class Status(models.TextChoices):
        AVAILABLE = "available", "Disponible"
        SOLD = "sold", "Vendido"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="jc_stock_emails",
        verbose_name="Dueño (inquilino)",
        null=True,
        blank=True,
    )
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="stock_emails",
        verbose_name="Servicio",
    )
    email = models.CharField("Correo / usuario", max_length=160)
    password = EncryptedTextField("Contraseña", blank=True)
    inventory_number = models.PositiveIntegerField(
        "Número de inventario", null=True, blank=True, editable=False,
    )
    status = models.CharField(
        "Estado", max_length=12, choices=Status.choices, default=Status.AVAILABLE,
    )
    acquisition_method = models.CharField(
        "Método de adquisición", max_length=120, blank=True,
    )
    customer_name = models.CharField("Cliente", max_length=160, blank=True)
    notes = models.CharField("Notas", max_length=200, blank=True)
    created_at = models.DateTimeField("Creado", auto_now_add=True)
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Correo en stock"
        verbose_name_plural = "Correos en stock"
        ordering = ["service__name", "status", "inventory_number", "email"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "service", "email"],
                name="uniq_stock_email_per_owner_service",
            ),
            models.UniqueConstraint(
                fields=["owner", "service", "inventory_number"],
                name="uniq_stock_number_per_owner_service",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="available")
                    | ~models.Q(customer_name="")
                ),
                name="sold_stock_email_requires_customer",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.service} · {self.email} ({self.get_status_display()})"

    @property
    def is_available(self) -> bool:
        return self.status == self.Status.AVAILABLE

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        self.acquisition_method = (self.acquisition_method or "").strip()
        self.customer_name = (self.customer_name or "").strip()
        if self.status == self.Status.AVAILABLE:
            self.customer_name = ""
        if self.inventory_number or not self.owner_id or not self.service_id:
            return super().save(*args, **kwargs)
        for _attempt in range(3):
            last_number = (
                StockEmail.objects.filter(owner_id=self.owner_id, service_id=self.service_id)
                .aggregate(last=models.Max("inventory_number"))["last"]
                or 0
            )
            self.inventory_number = last_number + 1
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                self.inventory_number = None
        raise IntegrityError("No se pudo asignar un número único al correo.")


class Transaction(models.Model):
    """Movimiento del libro de caja: ingreso (verde) o egreso (rojo)."""

    class Kind(models.TextChoices):
        INCOME = "income", "Ingreso"
        EXPENSE = "expense", "Egreso"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="jc_transactions",
        verbose_name="Dueño (inquilino)",
        null=True,
        blank=True,
    )
    kind = models.CharField("Tipo", max_length=10, choices=Kind.choices)
    amount = models.DecimalField("Monto", max_digits=10, decimal_places=2)
    currency = models.CharField("Moneda original", max_length=8, choices=CURRENCY_CHOICES, default="PEN")
    exchange_rate = models.DecimalField(
        "Tipo de cambio", max_digits=18, decimal_places=8, default=Decimal("1"),
        help_text="Cuánto vale 1 unidad de la moneda original en la moneda principal.",
    )
    base_currency = models.CharField(
        "Moneda principal al registrar", max_length=8, choices=CURRENCY_CHOICES, default="PEN"
    )
    base_amount = models.DecimalField(
        "Monto convertido", max_digits=18, decimal_places=2, default=Decimal("0.00")
    )
    description = models.CharField("Descripción", max_length=200, blank=True)
    client = models.ForeignKey(
        Client, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="transactions", verbose_name="Cliente",
    )
    subscription = models.ForeignKey(
        Subscription, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="transactions", verbose_name="Suscripción",
    )
    occurred_at = models.DateTimeField("Fecha", default=timezone.now)
    created_at = models.DateTimeField("Creado", auto_now_add=True)

    class Meta:
        verbose_name = "Movimiento"
        verbose_name_plural = "Movimientos (ingresos / egresos)"
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["owner", "-occurred_at"], name="tx_owner_occurred_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gte=0, base_amount__gte=0), name="transaction_amounts_nonnegative"),
            models.CheckConstraint(condition=models.Q(exchange_rate__gt=0), name="transaction_exchange_rate_gt_0"),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.amount} {self.currency}"

    def set_conversion(self, base_currency, exchange_rate=Decimal("1")):
        self.currency = normalize_currency(self.currency)
        self.base_currency = normalize_currency(base_currency)
        self.exchange_rate = Decimal(str(exchange_rate or 1))
        if self.currency == self.base_currency:
            self.exchange_rate = Decimal("1")
        self.base_amount = (self.amount * self.exchange_rate).quantize(Decimal("0.01"))

    def save(self, *args, **kwargs):
        if not self.base_amount and self.amount:
            base = "PEN"
            if self.owner_id:
                control = ControlSettings.objects.filter(owner_id=self.owner_id).only("currency").first()
                if control:
                    base = control.currency
            self.set_conversion(base, self.exchange_rate)
        super().save(*args, **kwargs)


class ControlSettings(models.Model):
    """Ajustes por inquilino de Jheliz Control (créditos del revendedor, divisa)."""

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="jc_settings",
        verbose_name="Dueño (inquilino)",
        null=True,
        blank=True,
    )
    credits = models.DecimalField(
        "Mis créditos", max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    country = models.CharField("País", max_length=2, default="PE")
    currency = models.CharField("Moneda principal", max_length=8, choices=CURRENCY_CHOICES, default="PEN")

    class Meta:
        verbose_name = "Ajustes de Jheliz Control"
        verbose_name_plural = "Ajustes de Jheliz Control"

    def __str__(self) -> str:
        return f"Ajustes de {self.owner_id or 'Jheliz Control'}"

    @classmethod
    def load(cls, owner=None) -> "ControlSettings":
        """Devuelve (o crea) los ajustes del inquilino dado.

        Sin ``owner`` mantiene el comportamiento antiguo (singleton pk=1) para
        no romper usos legados.
        """
        if owner is not None:
            obj, _ = cls.objects.get_or_create(owner=owner)
            return obj
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class TelegramConnection(models.Model):
    """Vínculo seguro entre un revendedor y el bot central de alertas."""

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="jc_telegram_connection",
    )
    chat_id = models.CharField(max_length=32, unique=True, null=True, blank=True)
    telegram_username = models.CharField(max_length=64, blank=True)
    link_token_digest = models.CharField(max_length=64, blank=True)
    link_expires_at = models.DateTimeField(null=True, blank=True)
    is_enabled = models.BooleanField(default=True)
    notify_windows = models.JSONField(default=list, blank=True)
    last_digest_date = models.DateField(null=True, blank=True)
    linked_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Telegram de revendedor"
        verbose_name_plural = "Telegram de revendedores"

    @property
    def is_linked(self):
        return bool(self.chat_id)

    def windows(self):
        values = self.notify_windows or [7, 3, 1, 0]
        return [int(value) for value in values if int(value) in {7, 3, 1, 0}]


class WhatsAppConnection(models.Model):
    """Numero de WhatsApp Business conectado por cada revendedor."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        ACTIVE = "active", "Activo"
        ERROR = "error", "Con error"
        DISCONNECTED = "disconnected", "Desconectado"

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="jc_whatsapp_connection",
    )
    access_token = EncryptedTextField(blank=True)
    waba_id = models.CharField(max_length=40, blank=True, db_index=True)
    phone_number_id = models.CharField(max_length=40, blank=True, unique=True, null=True)
    display_phone_number = models.CharField(max_length=40, blank=True)
    verified_name = models.CharField(max_length=160, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    is_enabled = models.BooleanField(default=True)
    template_name = models.CharField(max_length=128, default="recordatorio_vencimiento")
    template_language = models.CharField(max_length=16, default="es")
    reminder_days = models.JSONField(default=list, blank=True)
    last_error = models.TextField(blank=True)
    connected_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def windows(self):
        values = self.reminder_days or [1]
        return sorted({int(v) for v in values if int(v) in {7, 3, 1, 0}}, reverse=True)

    @property
    def is_connected(self):
        return bool(
            self.status == self.Status.ACTIVE and self.is_enabled
            and self.access_token and self.waba_id and self.phone_number_id
        )


class WhatsAppReminderDelivery(models.Model):
    """Entrega idempotente y estados reportados por Cloud API."""

    class Status(models.TextChoices):
        QUEUED = "queued", "En cola"
        SENT = "sent", "Enviado"
        DELIVERED = "delivered", "Entregado"
        READ = "read", "Leido"
        FAILED = "failed", "Fallido"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="jc_whatsapp_deliveries",
    )
    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="whatsapp_deliveries",
    )
    expiry_date = models.DateField()
    reminder_days = models.PositiveSmallIntegerField(default=1)
    recipient = models.CharField(max_length=40)
    template_name = models.CharField(max_length=128)
    meta_message_id = models.CharField(max_length=160, blank=True, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "expiry_date", "reminder_days"],
                name="uniq_whatsapp_reminder_cycle",
            ),
        ]


class TelegramSession(models.Model):
    """Estado efímero de navegación del bot, asociado al revendedor vinculado."""

    connection = models.OneToOneField(
        TelegramConnection,
        on_delete=models.CASCADE,
        related_name="session",
    )
    state = models.CharField(max_length=48, blank=True)
    data = models.JSONField(default=dict, blank=True)
    menu_message_id = models.BigIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sesión de Telegram"
        verbose_name_plural = "Sesiones de Telegram"


class TelegramActionReceipt(models.Model):
    """Registro de operaciones críticas para impedir ejecuciones duplicadas."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="jc_telegram_action_receipts",
    )
    key = models.CharField(max_length=80)
    action = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "key"],
                name="uniq_telegram_action_per_owner",
            )
        ]
        indexes = [
            models.Index(fields=["created_at"], name="telegram_action_created_idx")
        ]


class SupportContact(models.Model):
    """Enlace privado que conecta un cliente final con el soporte de su revendedor."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="jc_support_contacts",
    )
    client = models.OneToOneField(
        Client, on_delete=models.CASCADE, related_name="support_contact",
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    telegram_chat_id = models.CharField(max_length=32, blank=True, db_index=True)
    telegram_username = models.CharField(max_length=64, blank=True)
    linked_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Contacto de soporte"
        verbose_name_plural = "Contactos de soporte"


class SupportTicket(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Nuevo"
        OPEN = "open", "En atención"
        WAITING = "waiting", "Esperando cliente"
        RESOLVED = "resolved", "Resuelto"

    class Priority(models.TextChoices):
        NORMAL = "normal", "Normal"
        URGENT = "urgent", "Urgente"

    class Category(models.TextChoices):
        ACCESS = "access", "No puedo ingresar"
        PASSWORD = "password", "Contraseña incorrecta"
        BLOCKED = "blocked", "Cuenta o perfil bloqueado"
        CODE = "code", "Código de acceso"
        DEVICE = "device", "Pantalla o dispositivo"
        RENEWAL = "renewal", "Renovación o vencimiento"
        OTHER = "other", "Otro problema"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="jc_support_tickets",
    )
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="support_tickets",
    )
    subscription = models.ForeignKey(
        Subscription, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="support_tickets",
    )
    number = models.PositiveIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    category = models.CharField(max_length=16, choices=Category.choices, default=Category.OTHER)
    subject = models.CharField(max_length=160, blank=True)
    customer_chat_id = models.CharField(max_length=32, blank=True, db_index=True)
    last_message_at = models.DateTimeField(default=timezone.now, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_message_at"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "number"], name="uniq_support_ticket_number")
        ]
        indexes = [
            models.Index(fields=["owner", "status", "-last_message_at"], name="support_owner_status_idx")
        ]

    @property
    def display_number(self):
        return f"S-{self.number:04d}"


class SupportMessage(models.Model):
    class Sender(models.TextChoices):
        CUSTOMER = "customer", "Cliente"
        AGENT = "agent", "Distribuidor"
        SYSTEM = "system", "Sistema"

    ticket = models.ForeignKey(
        SupportTicket, on_delete=models.CASCADE, related_name="messages",
    )
    sender = models.CharField(max_length=10, choices=Sender.choices)
    text = models.TextField()
    telegram_message_id = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class SupportCustomerSession(models.Model):
    telegram_chat_id = models.CharField(max_length=32, unique=True)
    contact = models.ForeignKey(
        SupportContact, on_delete=models.CASCADE, related_name="customer_sessions",
    )
    state = models.CharField(max_length=48, blank=True)
    data = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class ResellerPaymentMethod(models.Model):
    class Kind(models.TextChoices):
        YAPE = "yape", "Yape"
        PLIN = "plin", "Plin"
        BANK = "bank", "Transferencia bancaria"
        USDT = "usdt", "USDT"
        PAYPAL = "paypal", "PayPal"
        ZELLE = "zelle", "Zelle"
        MERCADOPAGO = "mercadopago", "Mercado Pago"
        OTHER = "other", "Otro"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="jc_payment_methods",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    label = models.CharField(max_length=80)
    holder = models.CharField(max_length=120, blank=True)
    details = models.TextField(help_text="Número, cuenta, wallet o instrucciones de pago.")
    qr_image = models.ImageField(upload_to="jheliz_control/payment_methods/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "label"]


class RenewalRequest(models.Model):
    class Status(models.TextChoices):
        INVITED = "invited", "Enlace enviado"
        DECLINED = "declined", "No renovará"
        PAYMENT_PENDING = "payment_pending", "Esperando pago"
        PROOF_SENT = "proof_sent", "Pago por verificar"
        APPROVED = "approved", "Aprobado"
        REJECTED = "rejected", "Rechazado"
        HELP = "help", "Necesita ayuda"

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="jc_renewal_requests",
    )
    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="renewal_requests",
    )
    expiry_date = models.DateField()
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.INVITED)
    payment_method = models.ForeignKey(
        ResellerPaymentMethod, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="renewal_requests",
    )
    proof = models.ImageField(
        upload_to="jheliz_control/renewal_proofs/",
        storage=private_media_storage,
        blank=True,
        null=True,
    )
    customer_note = models.CharField(max_length=500, blank=True)
    rejection_reason = models.CharField(max_length=500, blank=True)
    link_expires_at = models.DateTimeField(default=renewal_link_expiry)
    requested_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "expiry_date"], name="uniq_renewal_request_cycle"
            )
        ]

    @property
    def display_number(self):
        return f"R-{self.pk:05d}" if self.pk else "R-NUEVA"

    @property
    def link_expired(self):
        return timezone.now() > self.link_expires_at


class Tenant(models.Model):
    """Inquilino que **alquila** Jheliz Control (un negocio = un usuario/login).

    El acceso al panel depende de ``plan_expires_at``: mientras esté vigente, el
    inquilino opera normal; si vence, entra pero ve "suscripción vencida" hasta
    que pague de nuevo (cobro por Yape con aprobación manual del proveedor).

    Al registrarse, el inquilino arranca con ``TRIAL_DAYS`` días de prueba
    gratis (acceso completo sin pagar el primer mes).
    """

    TRIAL_DAYS = 30

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="jc_tenant",
        verbose_name="Usuario",
    )
    business_name = models.CharField("Nombre del negocio", max_length=120, blank=True)
    whatsapp = models.CharField("WhatsApp", max_length=40, blank=True)
    plan_expires_at = models.DateTimeField(
        "Alquiler vence", null=True, blank=True,
        help_text="Hasta cuándo tiene acceso pagado. Vacío = nunca pagó.",
    )
    is_blocked = models.BooleanField(
        "Bloqueado", default=False,
        help_text="Si está activo, el inquilino no puede entrar aunque haya pagado.",
    )
    is_demo = models.BooleanField(
        "Demo", default=False,
        help_text="Cuenta temporal de demostración con operaciones de escritura bloqueadas.",
    )
    last_activity_at = models.DateTimeField("Última actividad", null=True, blank=True)
    last_activity_path = models.CharField("Última sección", max_length=200, blank=True)
    created_at = models.DateTimeField("Creado", auto_now_add=True)

    class Meta:
        verbose_name = "Inquilino"
        verbose_name_plural = "Inquilinos"
        ordering = ["-created_at"]
        permissions = [
            ("manage_tenants", "Puede administrar todos los inquilinos y sus pagos"),
        ]

    def __str__(self) -> str:
        return self.business_name or self.user.get_username()

    @property
    def whatsapp_digits(self) -> str:
        import re
        return re.sub(r"\D", "", self.whatsapp or "")

    @property
    def subscription_active(self) -> bool:
        if self.is_blocked:
            return False
        return bool(self.plan_expires_at and self.plan_expires_at > timezone.now())

    @property
    def days_left(self) -> int:
        if not self.plan_expires_at:
            return 0
        secs = (self.plan_expires_at - timezone.now()).total_seconds()
        return max(0, int(secs // 86400))

    def start_trial(self, days: int = TRIAL_DAYS) -> None:
        """Otorga la prueba gratis inicial si el inquilino nunca tuvo acceso."""
        if self.plan_expires_at is None:
            self.plan_expires_at = add_service_duration(timezone.now(), int(days))
            self.save(update_fields=["plan_expires_at"])

    def extend(self, days: int = 30) -> None:
        """Suma días de alquiler (acumulativo si aún está vigente)."""
        base = (
            self.plan_expires_at
            if self.plan_expires_at and self.plan_expires_at > timezone.now()
            else timezone.now()
        )
        self.plan_expires_at = add_service_duration(base, int(days))
        self.save(update_fields=["plan_expires_at"])


class TenantActivity(models.Model):
    """Resumen mínimo de uso del panel, sin contenido privado ni secretos."""

    tenant = models.OneToOneField(
        Tenant, on_delete=models.CASCADE, related_name="activity"
    )
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(db_index=True)
    last_path = models.CharField(max_length=160, blank=True)
    total_requests = models.PositiveBigIntegerField(default=0)
    session_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Actividad de inquilino"
        verbose_name_plural = "Actividad de inquilinos"


class TenantActivityEvent(models.Model):
    """Acción funcional sanitizada; nunca almacena formularios ni credenciales."""

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="activity_events"
    )
    action = models.CharField(max_length=60, db_index=True)
    path = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["tenant", "-created_at"],
                name="gestion_act_tenant_created_idx",
            )
        ]


class TenantPayment(models.Model):
    """Pago de alquiler por **Yape** de un inquilino, con aprobación manual."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        APPROVED = "approved", "Aprobado"
        REJECTED = "rejected", "Rechazado"

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="payments",
        verbose_name="Inquilino",
    )
    amount = models.DecimalField("Monto", max_digits=10, decimal_places=2, default=Decimal("0.00"))
    days = models.PositiveIntegerField("Días que otorga", default=30)
    proof = models.ImageField(
        "Comprobante Yape", upload_to="jheliz_control/pagos/",
        storage=private_media_storage, blank=True,
        help_text="Captura del pago por Yape subida por el inquilino.",
    )
    status = models.CharField(
        "Estado", max_length=10, choices=Status.choices, default=Status.PENDING,
    )
    rejection_reason = models.CharField("Motivo de rechazo", max_length=200, blank=True)
    created_at = models.DateTimeField("Subido", auto_now_add=True)
    reviewed_at = models.DateTimeField("Revisado", null=True, blank=True)

    class Meta:
        verbose_name = "Pago de alquiler"
        verbose_name_plural = "Pagos de alquiler (Yape)"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Pago {self.tenant} S/ {self.amount} ({self.get_status_display()})"

    @property
    def is_pending(self) -> bool:
        return self.status == self.Status.PENDING

    def approve(self) -> None:
        self.status = self.Status.APPROVED
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "reviewed_at"])
        self.tenant.extend(self.days or 30)

    def reject(self, reason: str = "") -> None:
        self.status = self.Status.REJECTED
        self.rejection_reason = reason or ""
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "rejection_reason", "reviewed_at"])


class SaasSettings(models.Model):
    """Ajustes del **proveedor** (vos): precio del alquiler y datos de cobro."""

    monthly_price = models.DecimalField(
        "Precio mensual (S/)", max_digits=10, decimal_places=2, default=Decimal("30.00")
    )
    yape_holder = models.CharField("Titular", max_length=120, blank=True)
    yape_phone = models.CharField("Binance Pay ID / referencia", max_length=30, blank=True)
    yape_qr = models.ImageField(
        "QR de pago", upload_to="jheliz_control/yape/", blank=True,
        help_text="QR de pago (Binance Pay) para cobrar el alquiler.",
    )
    instructions = models.TextField("Instrucciones extra", blank=True)

    class Meta:
        verbose_name = "Ajustes del SaaS (Jheliz Control)"
        verbose_name_plural = "Ajustes del SaaS (Jheliz Control)"

    def __str__(self) -> str:
        return "Ajustes del SaaS"

    @classmethod
    def load(cls) -> "SaasSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
