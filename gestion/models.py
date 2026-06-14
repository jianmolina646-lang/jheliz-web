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

from django.conf import settings
from django.db import models
from django.utils import timezone


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
    account_password = models.CharField("Contraseña", max_length=160, blank=True)
    plan = models.CharField(
        "Plan", max_length=12, choices=Plan.choices, default=Plan.PERFIL
    )
    profiles = models.PositiveSmallIntegerField(
        "Perfiles", default=1,
        help_text="Cantidad de perfiles (1 a 7). En cuenta completa, 1.",
    )
    profile_name = models.CharField("Nombre de perfil", max_length=80, blank=True)
    profile_pin = models.CharField("PIN", max_length=12, blank=True)
    plan_label = models.CharField(
        "Plan de suscripción", max_length=40, blank=True,
        help_text="Nombre del plan (ej. Premium, Básico).",
    )

    # Finanzas (USD por defecto; la divisa se guarda por si se cambia a futuro).
    currency = models.CharField("Moneda", max_length=8, default="S/")
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
        """Suma días de forma acumulativa. Si ya venció, suma desde ahora."""
        base = self.expires_at if self.expires_at and self.expires_at > timezone.now() else timezone.now()
        self.expires_at = base + timedelta(days=int(days))
        self.save(update_fields=["expires_at", "updated_at"])


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
    currency = models.CharField("Moneda", max_length=8, default="S/")
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

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.amount} {self.currency}"


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
    currency = models.CharField("Moneda", max_length=8, default="S/")

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
    created_at = models.DateTimeField("Creado", auto_now_add=True)

    class Meta:
        verbose_name = "Inquilino"
        verbose_name_plural = "Inquilinos"
        ordering = ["-created_at"]

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
            self.plan_expires_at = timezone.now() + timedelta(days=int(days))
            self.save(update_fields=["plan_expires_at"])

    def extend(self, days: int = 30) -> None:
        """Suma días de alquiler (acumulativo si aún está vigente)."""
        base = (
            self.plan_expires_at
            if self.plan_expires_at and self.plan_expires_at > timezone.now()
            else timezone.now()
        )
        self.plan_expires_at = base + timedelta(days=int(days))
        self.save(update_fields=["plan_expires_at"])


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
        "Comprobante Yape", upload_to="jheliz_control/pagos/", blank=True,
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
    """Ajustes del **proveedor** (vos): precio del alquiler y Yape de cobro."""

    monthly_price = models.DecimalField(
        "Precio mensual (S/)", max_digits=10, decimal_places=2, default=Decimal("30.00")
    )
    yape_holder = models.CharField("Titular Yape", max_length=120, blank=True)
    yape_phone = models.CharField("Número Yape", max_length=30, blank=True)
    yape_qr = models.ImageField(
        "QR de Yape", upload_to="jheliz_control/yape/", blank=True,
        help_text="QR de tu Yape para cobrar el alquiler.",
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
