"""Modelos del bot de códigos.

El admin da de alta a cada cliente del bot (``CodeBotClient``) y le asigna
los correos de las cuentas que compró (``AssignedEmail``). El cliente, desde
Telegram, solo puede pedir el código de Netflix de los correos que tiene
asignados; nunca de cuentas ajenas.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class CodeBotClient(models.Model):
    """Un cliente autorizado a usar el bot de códigos.

    Se identifica por su ``telegram_chat_id``. Al hacer ``/start`` por primera
    vez queda creado pero ``is_active=False`` (pendiente); el admin lo activa
    y le asigna correos desde el panel.
    """

    telegram_chat_id = models.CharField(
        "Chat ID de Telegram", max_length=32, unique=True
    )
    telegram_username = models.CharField(
        "Usuario de Telegram", max_length=64, blank=True
    )
    display_name = models.CharField("Nombre", max_length=120, blank=True)
    is_active = models.BooleanField(
        "Activo",
        default=False,
        help_text="Si está desactivado, el bot no le entrega códigos.",
    )
    expires_at = models.DateTimeField(
        "Vence",
        null=True,
        blank=True,
        help_text="Cuando pasa esta fecha, el bot deja de entregarle códigos. Vacío = sin vencimiento.",
    )
    note = models.CharField("Nota interna", max_length=200, blank=True)
    created_at = models.DateTimeField("Alta", auto_now_add=True)
    last_seen_at = models.DateTimeField("Último uso", null=True, blank=True)

    class Meta:
        verbose_name = "Cliente del bot de códigos"
        verbose_name_plural = "Clientes del bot de códigos"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        label = self.display_name or self.telegram_username or self.telegram_chat_id
        return f"{label} ({self.telegram_chat_id})"

    def touch(self) -> None:
        """Marca el último uso sin disparar señales pesadas."""
        self.last_seen_at = timezone.now()
        self.save(update_fields=["last_seen_at"])

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at <= timezone.now())

    @property
    def has_access(self) -> bool:
        return self.is_active and not self.is_expired


class AssignedEmail(models.Model):
    """Un correo de cuenta que el admin asignó a un cliente.

    Un mismo correo puede estar asignado a varios clientes (cuentas
    compartidas por perfiles), por eso la unicidad es por (cliente, correo).
    """

    client = models.ForeignKey(
        CodeBotClient,
        related_name="emails",
        on_delete=models.CASCADE,
        verbose_name="Cliente",
    )
    email = models.EmailField("Correo de la cuenta")
    note = models.CharField("Nota (plataforma/perfil)", max_length=120, blank=True)
    created_at = models.DateTimeField("Asignado", auto_now_add=True)

    class Meta:
        verbose_name = "Correo asignado"
        verbose_name_plural = "Correos asignados"
        ordering = ("email",)
        constraints = [
            models.UniqueConstraint(
                fields=["client", "email"], name="uniq_client_email"
            )
        ]

    def __str__(self) -> str:
        return f"{self.email} → {self.client_id}"

    def save(self, *args, **kwargs):
        # Normaliza el correo para que el match con la bandeja sea fiable.
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)


class DisneyBotClient(models.Model):
    """Cliente del bot Disney+, aislado del padrón del bot Netflix."""
    telegram_chat_id = models.CharField("Chat ID de Telegram", max_length=32, unique=True)
    telegram_username = models.CharField("Usuario de Telegram", max_length=64, blank=True)
    display_name = models.CharField("Nombre", max_length=120, blank=True)
    is_active = models.BooleanField("Activo", default=False)
    note = models.CharField("Nota interna", max_length=200, blank=True)
    created_at = models.DateTimeField("Alta", auto_now_add=True)
    last_seen_at = models.DateTimeField("Último uso", null=True, blank=True)

    class Meta:
        verbose_name = "Cliente del bot Disney+"
        verbose_name_plural = "Clientes del bot Disney+"
        ordering = ("-created_at",)

    def __str__(self):
        label = self.display_name or self.telegram_username or self.telegram_chat_id
        return f"{label} ({self.telegram_chat_id})"

    def touch(self):
        self.last_seen_at = timezone.now()
        self.save(update_fields=["last_seen_at"])


class DisneyAssignedEmail(models.Model):
    """Correo Disney+ asignado, independiente de las cuentas Netflix."""
    client = models.ForeignKey(DisneyBotClient, related_name="emails", on_delete=models.CASCADE, verbose_name="Cliente")
    email = models.EmailField("Correo de la cuenta")
    note = models.CharField("Nota", max_length=120, blank=True)
    created_at = models.DateTimeField("Asignado", auto_now_add=True)

    class Meta:
        verbose_name = "Correo Disney+ asignado"
        verbose_name_plural = "Correos Disney+ asignados"
        ordering = ("email",)
        constraints = [models.UniqueConstraint(fields=["client", "email"], name="uniq_disney_client_email")]

    def __str__(self):
        return f"{self.email} → {self.client_id}"

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)


class DisneyCodeDelivery(models.Model):
    """Auditoría y deduplicación de códigos del bot Disney+."""
    client = models.ForeignKey(DisneyBotClient, related_name="deliveries", on_delete=models.CASCADE, verbose_name="Cliente")
    email = models.EmailField("Correo de la cuenta")
    found = models.BooleanField("Entregado", default=False)
    payload_fingerprint = models.CharField("Huella del código", max_length=64, blank=True, db_index=True)
    duplicate = models.BooleanField("Código repetido", default=False)
    created_at = models.DateTimeField("Fecha", auto_now_add=True)

    class Meta:
        verbose_name = "Entrega de código Disney+"
        verbose_name_plural = "Entregas de códigos Disney+"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["client", "created_at"])]

    def __str__(self):
        return f"{'✓' if self.found else '✗'} {self.email} [Disney+] → {self.client_id}"


class CodeDelivery(models.Model):
    """Registro de auditoría: cada pedido de código que atendió el bot.

    Sirve para saber quién pidió qué, cuándo y si se le entregó algo, y para
    aplicar el límite diario de pedidos por cliente.
    """

    client = models.ForeignKey(
        CodeBotClient,
        related_name="deliveries",
        on_delete=models.CASCADE,
        verbose_name="Cliente",
    )
    email = models.EmailField("Correo de la cuenta")
    kind = models.CharField("Tipo pedido", max_length=32, blank=True)
    found = models.BooleanField("Entregado", default=False)
    payload_fingerprint = models.CharField(
        "Huella del resultado", max_length=64, blank=True, db_index=True
    )
    duplicate = models.BooleanField("Resultado repetido", default=False)
    created_at = models.DateTimeField("Fecha", auto_now_add=True)

    class Meta:
        verbose_name = "Entrega de código"
        verbose_name_plural = "Entregas de códigos"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["client", "created_at"]),
        ]

    def __str__(self) -> str:
        estado = "✓" if self.found else "✗"
        return f"{estado} {self.email} [{self.kind or 'any'}] → {self.client_id}"


class BotState(models.Model):
    """Estado persistente de cada bot (una fila por bot).

    Guarda el ``update_id`` de Telegram ya procesado para que, si el contenedor
    se reinicia, el bot no vuelva a procesar pedidos viejos: retoma desde el
    último update confirmado. Cada bot usa su propia fila (``pk``): el de
    Netflix ``pk=1`` y el de Disney+ ``pk=2``, así sus offsets no se pisan.
    """

    telegram_offset = models.BigIntegerField("Último update de Telegram", default=0)
    daily_limit = models.PositiveIntegerField(
        "Límite diario de consultas",
        null=True,
        blank=True,
        help_text="Vacío = usar CODES_DAILY_LIMIT de la configuración.",
    )
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Estado del bot de códigos"
        verbose_name_plural = "Estado del bot de códigos"

    def __str__(self) -> str:
        return f"BotState(pk={self.pk}, offset={self.telegram_offset})"

    @classmethod
    def get_offset(cls, pk: int = 1) -> int:
        row = cls.objects.filter(pk=pk).first()
        return row.telegram_offset if row else 0

    @classmethod
    def set_offset(cls, offset: int, pk: int = 1) -> None:
        cls.objects.update_or_create(
            pk=pk, defaults={"telegram_offset": int(offset)}
        )
