import secrets
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class Category(models.Model):
    class Audience(models.TextChoices):
        CLIENTE = "cliente", "Cliente final (perfiles)"
        DISTRIBUIDOR = "distribuidor", "Distribuidor (cuentas completas)"
        AMBOS = "ambos", "Ambos"

    name = models.CharField("Nombre", max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    emoji = models.CharField("Emoji", max_length=8, blank=True, default="\U0001f389")
    description = models.TextField("Descripci\u00f3n", blank=True)
    audience = models.CharField(
        "P\u00fablico",
        max_length=20,
        choices=Audience.choices,
        default=Audience.AMBOS,
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("order", "name")
        verbose_name = "Categor\u00eda"
        verbose_name_plural = "Categor\u00edas"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("catalog:category", args=[self.slug])


class ProductMode(models.TextChoices):
    PERFIL = "perfil", "Cuenta compartida (por perfil)"
    COMPLETA = "completa", "Cuenta completa"
    LICENCIA = "licencia", "Licencia / c\u00f3digo"


class Product(models.Model):
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products"
    )
    name = models.CharField("Nombre", max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    mode = models.CharField(
        "Modo de venta", max_length=20,
        choices=ProductMode.choices, default=ProductMode.PERFIL,
    )
    short_description = models.CharField("Descripci\u00f3n corta", max_length=180, blank=True)
    description = models.TextField("Descripci\u00f3n", blank=True)
    icon = models.CharField("Emoji/icono", max_length=8, blank=True)
    image = models.ImageField("Imagen", upload_to="products/", blank=True, null=True)
    is_active = models.BooleanField("Visible en tienda", default=True)
    is_featured = models.BooleanField("Destacado en home", default=False)

    class TelegramAudience(models.TextChoices):
        BOTH = "both", "Ambos canales (clientes + distribuidores)"
        CUSTOMER = "customer", "Solo canal de clientes"
        DISTRIBUTOR = "distributor", "Solo canal de distribuidores"
        NONE = "none", "No publicar en ningún canal"

    telegram_audience = models.CharField(
        "Publicar en Telegram",
        max_length=20,
        choices=TelegramAudience.choices,
        default=TelegramAudience.BOTH,
        help_text=(
            "Elige a qué canal(es) se publica este producto cuando se activa "
            "o se usa la acción 'Publicar al canal' del admin."
        ),
    )
    delivery_is_instant = models.BooleanField(
        "Entrega inmediata", default=False,
        help_text="Si est\u00e1 activo, se asigna un stock autom\u00e1ticamente. Por defecto, "
        "la entrega es manual y el admin crea el perfil con los datos que pidi\u00f3 el cliente.",
    )
    requires_customer_profile_data = models.BooleanField(
        "Pedir al cliente nombre de perfil y PIN", default=True,
        help_text="Aplica a productos por perfil (Netflix, Disney, etc). "
        "Desactiva para licencias donde el cliente no elige nada.",
    )
    rating = models.DecimalField(
        "Rating mostrado", max_digits=3, decimal_places=1, default=Decimal("5.0")
    )
    sold_badge = models.CharField(
        "Etiqueta de ventas", max_length=20, blank=True,
        help_text="Ej: +500, +10K",
    )
    whatsapp_sales_copy = models.TextField(
        "Plantilla para WhatsApp (distribuidores)", blank=True,
        help_text=(
            "Texto pre-armado que el distribuidor copia al instante para reenviar"
            " a sus clientes finales. Si está vacío se genera uno automático con"
            " nombre del producto y precios. Podés usar emojis y saltos de línea."
        ),
    )
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("order", "name")
        verbose_name = "Producto"
        verbose_name_plural = "Productos"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:140]
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("catalog:product", args=[self.slug])

    def whatsapp_pitch_for(self, user=None) -> str:
        """Texto pre-armado para que un distribuidor lo reenvíe a su cliente final.

        Si el admin configuró un copy personalizado en `whatsapp_sales_copy`, se
        usa ese. Si no, generamos uno con el nombre del producto y los planes
        visibles para el cliente final (usa precio público, no mayorista).
        """
        if self.whatsapp_sales_copy.strip():
            return self.whatsapp_sales_copy
        from django.conf import settings

        currency = getattr(settings, "DEFAULT_CURRENCY_SYMBOL", "S/")
        lines = [f"{self.icon or '🎬'} *{self.name}*"]
        if self.short_description:
            lines.append(self.short_description)
        plans = self.plans.filter(is_active=True, available_for_customer=True).order_by("order", "duration_days")
        for plan in plans:
            if plan.price_customer <= 0:
                continue
            duration = f"{plan.duration_days} días" if plan.duration_days else "sin expiración"
            lines.append(f"• {plan.name} ({duration}) — {currency} {plan.price_customer:.2f}")
        lines.append("")
        lines.append("✅ Garantía durante toda la suscripción")
        lines.append("✅ Entrega rápida")
        lines.append("")
        lines.append("DM para apartar 👇")
        return "\n".join(lines)

    def price_for(self, user) -> Decimal | None:
        """Precio m\u00ednimo visible para el usuario actual."""
        plan = self.cheapest_visible_plan(user)
        if not plan:
            return None
        return plan.price_for(user)

    def active_plans(self, user=None):
        qs = self.plans.filter(is_active=True)
        if user and getattr(user, "is_distributor", False):
            return qs
        return qs.filter(available_for_customer=True)

    def cheapest_visible_plan(self, user=None):
        """Plan m\u00e1s barato visible al usuario, ignorando precios en 0.

        Sirve para mostrar el `DESDE S/ X` en cards y SEO titles sin que
        un plan en S/ 0 o un plan oculto contamine la vista p\u00fablica.
        """
        plans = [
            p
            for p in self.active_plans(user)
            if (p.price_distributor if user and getattr(user, "is_distributor", False) else p.price_customer) > 0
        ]
        if not plans:
            return None
        if user and getattr(user, "is_distributor", False):
            return min(plans, key=lambda p: p.price_distributor)
        return min(plans, key=lambda p: p.price_customer)

    @property
    def available_stock(self) -> int:
        """Cuenta TODOS los stock items disponibles del producto.

        Incluye tanto stock atado a un plan espec\u00edfico como stock gen\u00e9rico
        (sin plan), porque a nivel producto cualquier StockItem disponible
        cuenta para urgencia / badge "Quedan X".
        """
        return self.stock_items.filter(status=StockItem.Status.AVAILABLE).count()

    @property
    def low_stock_threshold(self) -> int:
        """M\u00e1ximo umbral de stock bajo entre los planes del producto.

        Sirve como gatillo para mostrar el badge de urgencia en la tarjeta
        del producto. Si ning\u00fan plan define umbral, usa 5 por defecto.
        """
        thresholds = [p.low_stock_threshold for p in self.plans.all() if p.low_stock_threshold]
        return max(thresholds) if thresholds else 5

    @property
    def is_low_stock(self) -> bool:
        """True si queda poco stock disponible (gatilla badge de urgencia)."""
        stock = self.available_stock
        return 0 < stock <= self.low_stock_threshold

    @property
    def stock_urgency_level(self) -> str:
        """`critical` (\u22642), `low` (\u22645), o `''` si hay holgura."""
        stock = self.available_stock
        if stock <= 0:
            return ""
        if stock <= 2:
            return "critical"
        if stock <= self.low_stock_threshold:
            return "low"
        return ""


class Plan(models.Model):
    """Variante de un producto: duraci\u00f3n y precio."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="plans")
    name = models.CharField("Nombre", max_length=80, help_text="Ej: 1 mes, 3 meses, Licencia de por vida")
    duration_days = models.PositiveIntegerField(
        "Duraci\u00f3n en d\u00edas", default=30,
        help_text="0 = sin expiraci\u00f3n (licencias perpetuas).",
    )
    price_customer = models.DecimalField(
        "Precio cliente (S/)", max_digits=10, decimal_places=2
    )
    price_distributor = models.DecimalField(
        "Precio distribuidor (S/)", max_digits=10, decimal_places=2,
        default=Decimal("0.00"),
    )
    available_for_customer = models.BooleanField("Visible cliente final", default=True)
    available_for_distributor = models.BooleanField("Visible distribuidor", default=True)
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(
        "Umbral de stock bajo", default=3,
        help_text="Cuando el stock disponible cae por debajo de este número, "
                  "se envía una alerta por Telegram al admin.",
    )
    low_stock_alert_sent_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ("order", "duration_days")
        verbose_name = "Plan"
        verbose_name_plural = "Planes"

    def __str__(self) -> str:
        return f"{self.product.name} \u2014 {self.name}"

    def price_for(self, user) -> Decimal:
        if user and getattr(user, "is_distributor", False) and self.price_distributor > 0:
            return self.price_distributor
        return self.price_customer

    @property
    def available_stock(self) -> int:
        return self.stock_items.filter(status=StockItem.Status.AVAILABLE).count()

    @property
    def is_low_stock(self) -> bool:
        stock = self.available_stock
        return 0 < stock <= (self.low_stock_threshold or 0)


class CustomerPlan(Plan):
    """Vista del Plan enfocada en cliente final (precio y visibilidad cliente)."""

    class Meta:
        proxy = True
        verbose_name = "Plan — Cliente final"
        verbose_name_plural = "Planes — Cliente final"


class DistributorPlan(Plan):
    """Vista mayorista del Plan (precio y visibilidad distribuidor)."""

    class Meta:
        proxy = True
        verbose_name = "Plan — Distribuidor"
        verbose_name_plural = "Planes — Distribuidor"


class StockItem(models.Model):
    """Una credencial concreta lista para entregar."""

    class Status(models.TextChoices):
        AVAILABLE = "available", "Disponible"
        RESERVED = "reserved", "Reservada"
        SOLD = "sold", "Vendida"
        DEFECTIVE = "defective", "Caída / Reportada"
        DISABLED = "disabled", "Deshabilitada"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="stock_items")
    plan = models.ForeignKey(
        Plan, on_delete=models.CASCADE, related_name="stock_items",
        null=True, blank=True,
        help_text="Si queda en blanco, el stock sirve para cualquier plan del producto.",
    )
    credentials = models.TextField(
        "Credenciales",
        help_text="Texto libre que recibir\u00e1 el cliente. Ej:\n"
                  "Correo: foo@bar.com\nContrase\u00f1a: 1234\nPerfil: Perfil 2\nPIN: 0000",
    )
    label = models.CharField("Etiqueta interna", max_length=80, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    created_at = models.DateTimeField(auto_now_add=True)
    sold_at = models.DateTimeField(null=True, blank=True)
    # Cuándo vence la cuenta en el proveedor (no en el cliente). Sirve
    # para alertar antes de que se muera la cuenta original y rotarla
    # con tiempo. El campo es opcional y sólo aplica para cuentas con
    # vencimiento conocido.
    provider_expires_at = models.DateTimeField(
        "Vencimiento en proveedor", null=True, blank=True,
        help_text="Cuándo vence la cuenta original (no la del cliente).",
    )
    # Marcas para evitar mandar el mismo aviso varias veces. Las setea
    # el management command notify_provider_expiry.
    provider_expiry_3d_notified_at = models.DateTimeField(null=True, blank=True)
    provider_expiry_1d_notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Stock"
        verbose_name_plural = "Stock"
        indexes = [
            models.Index(fields=["product", "status"]),
            models.Index(fields=["plan", "status"]),
            models.Index(fields=["provider_expires_at"], name="stock_provexp_idx"),
        ]

    def __str__(self) -> str:
        plan = self.plan.name if self.plan else "cualquier plan"
        return f"{self.product.name} \u2014 {plan} \u2014 {self.get_status_display()}"


class Testimonial(models.Model):
    author = models.CharField("Autor", max_length=80)
    city = models.CharField("Ciudad", max_length=80, default="Lima")
    text = models.TextField("Reseña")
    rating = models.PositiveSmallIntegerField("Estrellas", default=5)
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="testimonials", verbose_name="Producto",
    )
    is_published = models.BooleanField("Publicada", default=True)
    order = models.PositiveIntegerField("Orden", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("order", "-created_at")
        verbose_name = "Reseña"
        verbose_name_plural = "Reseñas"

    def __str__(self) -> str:
        return f"{self.author} ({self.rating}★)"


def _generate_review_token() -> str:
    return secrets.token_urlsafe(24)


class ProductReview(models.Model):
    """Reseña enviada por un cliente con compra verificada.

    Se crea v\u00eda link m\u00e1gico que se manda por correo cuando el pedido
    pasa a *Entregado*. El cliente puede subir una foto opcional. Las rese\u00f1as
    pasan por moderaci\u00f3n antes de mostrarse en la ficha de producto.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente moderaci\u00f3n"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="reviews",
        verbose_name="Producto",
    )
    order = models.ForeignKey(
        "orders.Order", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviews", verbose_name="Pedido",
        help_text="Pedido que origin\u00f3 la rese\u00f1a (verificaci\u00f3n).",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="reviews",
    )
    author_name = models.CharField("Nombre", max_length=80)
    email = models.EmailField("Correo", blank=True)
    city = models.CharField("Ciudad", max_length=80, blank=True, default="")
    rating = models.PositiveSmallIntegerField(
        "Estrellas", default=5,
        choices=[(i, f"{i} \u2605") for i in range(1, 6)],
    )
    title = models.CharField("T\u00edtulo", max_length=120, blank=True)
    comment = models.TextField("Comentario")
    photo = models.ImageField(
        "Foto", upload_to="reviews/", blank=True, null=True,
        help_text="Captura o foto opcional (m\u00e1x. ~2MB).",
    )
    is_verified = models.BooleanField(
        "Compra verificada", default=False,
        help_text="True si la rese\u00f1a est\u00e1 ligada a un pedido entregado.",
    )
    status = models.CharField(
        "Estado", max_length=12, choices=Status.choices, default=Status.PENDING,
        db_index=True,
    )
    moderation_notes = models.TextField("Notas internas", blank=True)
    token = models.CharField(
        "Token", max_length=48, unique=True, default=_generate_review_token,
        editable=False,
        help_text="Token \u00fanico para el link m\u00e1gico de env\u00edo.",
    )
    token_used_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Rese\u00f1a verificada"
        verbose_name_plural = "Rese\u00f1as verificadas"
        indexes = [
            models.Index(fields=["product", "status"], name="review_prod_status_idx"),
            models.Index(fields=["status", "-created_at"], name="review_status_created_idx"),
        ]

    def __str__(self) -> str:
        verified = " \u2713" if self.is_verified else ""
        return f"{self.author_name} ({self.rating}\u2605) \u2014 {self.product.name}{verified}"

    def get_absolute_url(self) -> str:
        return reverse("catalog:review_submit", args=[self.token])

    def mark_used(self) -> None:
        if self.token_used_at is None:
            self.token_used_at = timezone.now()
            self.save(update_fields=["token_used_at"])


class PromoBanner(models.Model):
    """Banner promocional editable que se muestra arriba del header.

    El admin puede programar fechas, color, texto y c\u00f3digo de cup\u00f3n.
    Se oculta autom\u00e1ticamente cuando expira.
    """

    class Style(models.TextChoices):
        PINK = "pink", "Rosa Jheliz (recomendado)"
        DARK = "dark", "Negro"
        AMBER = "amber", "\u00c1mbar / oferta"
        EMERALD = "emerald", "Verde / nuevo"
        SLATE = "slate", "Gris claro"

    name = models.CharField(
        "Nombre interno", max_length=80,
        help_text="Solo para identificarlo en el admin, ej: 'Black Friday 2026'.",
    )
    text = models.CharField(
        "Texto", max_length=180,
        help_text="Texto principal del banner. Soporta emojis.",
    )
    coupon_code = models.CharField(
        "C\u00f3digo de cup\u00f3n", max_length=40, blank=True,
        help_text="Si se llena, se muestra un bot\u00f3n 'Copiar c\u00f3digo'.",
    )
    cta_label = models.CharField(
        "Texto del bot\u00f3n", max_length=40, blank=True, default="Ver ofertas",
    )
    cta_url = models.CharField(
        "URL del bot\u00f3n", max_length=200, blank=True,
        help_text="Ruta relativa (ej. /productos/) o URL completa.",
    )
    countdown_to = models.DateTimeField(
        "Cuenta regresiva hasta", null=True, blank=True,
        help_text="Si se llena, se muestra un contador. Suele coincidir con 'Termina'.",
    )
    style = models.CharField(
        "Estilo", max_length=10, choices=Style.choices, default=Style.PINK,
    )
    is_active = models.BooleanField("Activo", default=True)
    starts_at = models.DateTimeField(
        "Empieza", null=True, blank=True,
        help_text="Vac\u00edo = empieza inmediatamente.",
    )
    ends_at = models.DateTimeField(
        "Termina", null=True, blank=True,
        help_text="Vac\u00edo = sin fecha de fin (siempre visible mientras est\u00e9 activo).",
    )
    show_only_on_home = models.BooleanField(
        "Solo en la p\u00e1gina de inicio", default=False,
        help_text="Si lo desactivas, se muestra en todas las p\u00e1ginas.",
    )
    order = models.PositiveIntegerField("Orden", default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("order", "-created_at")
        verbose_name = "Banner promocional"
        verbose_name_plural = "Banners promocionales"

    def __str__(self) -> str:
        return self.name

    @property
    def is_currently_active(self) -> bool:
        if not self.is_active:
            return False
        now = timezone.now()
        if self.starts_at and self.starts_at > now:
            return False
        if self.ends_at and self.ends_at <= now:
            return False
        return True

    @classmethod
    def get_active(cls, *, on_home: bool = False) -> "PromoBanner | None":
        """Devuelve el banner activo de mayor prioridad para esta vista."""
        now = timezone.now()
        qs = cls.objects.filter(is_active=True)
        qs = qs.filter(models.Q(starts_at__isnull=True) | models.Q(starts_at__lte=now))
        qs = qs.filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gt=now))
        if not on_home:
            qs = qs.filter(show_only_on_home=False)
        return qs.order_by("order", "-created_at").first()


class SiteSettings(models.Model):
    """Configuración global del sitio editable desde el admin (singleton).

    Permite cambiar logo, textos del hero, link de WhatsApp, redes sociales,
    etc. sin tocar código.
    """

    site_name = models.CharField(
        "Nombre del sitio", max_length=80, default="Jheliz",
        help_text="Aparece en el header, footer y emails.",
    )
    tagline = models.CharField(
        "Tagline corto", max_length=160, blank=True,
        default="Cuentas oficiales y licencias premium en Perú",
    )
    logo = models.ImageField(
        "Logo", upload_to="site/", blank=True, null=True,
        help_text="Reemplaza el logo del header. PNG transparente recomendado (200×60).",
    )
    favicon = models.ImageField(
        "Favicon", upload_to="site/", blank=True, null=True,
        help_text="Icono de la pestaña del navegador. ICO o PNG 64×64.",
    )

    # Hero / portada
    hero_title = models.CharField(
        "Título del hero", max_length=120, blank=True,
        default="Streaming y licencias premium",
    )
    hero_subtitle = models.CharField(
        "Subtítulo del hero", max_length=200, blank=True,
        default="Netflix, Disney+, Spotify, Office y más — cuentas oficiales con garantía.",
    )
    hero_cta_text = models.CharField(
        "Texto del botón CTA", max_length=40, default="Ver catálogo",
    )

    # Contacto
    whatsapp_number = models.CharField(
        "WhatsApp (con código país, sin +)", max_length=20, blank=True,
        default="51999999999",
        help_text="Ej: 51999999999 (sin + ni espacios). Se usa en el botón flotante.",
    )
    whatsapp_message = models.CharField(
        "Mensaje pre-rellenado de WhatsApp", max_length=200,
        default="Hola Jheliz, tengo una consulta sobre sus productos.",
    )
    contact_email = models.EmailField("Correo de contacto", blank=True)

    # Redes sociales
    instagram_url = models.URLField("Instagram", blank=True)
    tiktok_url = models.URLField("TikTok", blank=True)
    facebook_url = models.URLField("Facebook", blank=True)
    youtube_url = models.URLField("YouTube", blank=True)

    # Canales de Telegram (públicos)
    telegram_customer_channel_url = models.URLField(
        "Canal Telegram – clientes", blank=True,
        default="https://t.me/jheliztvavisos",
        help_text="Canal público de avisos para clientes finales (ofertas, novedades).",
    )
    telegram_distributor_channel_url = models.URLField(
        "Canal Telegram – distribuidores", blank=True,
        default="https://t.me/jhelizservicetv",
        help_text="Canal público con info y avisos para distribuidores.",
    )

    # Información legal (Indecopi Perú)
    legal_business_name = models.CharField(
        "Razón social", max_length=160, blank=True,
        help_text="Nombre legal de la empresa, ej: 'Jheliz Services E.I.R.L.'",
    )
    legal_ruc = models.CharField(
        "RUC", max_length=20, blank=True,
        help_text="11 dígitos del RUC de la empresa.",
    )
    legal_address = models.CharField(
        "Dirección física", max_length=200, blank=True,
    )

    # SEO global
    seo_default_image = models.ImageField(
        "Imagen OG por defecto", upload_to="site/", blank=True, null=True,
        help_text="Imagen que aparece al compartir el sitio en WhatsApp/Facebook (1200×630).",
    )
    seo_meta_description = models.CharField(
        "Meta descripción (SEO)", max_length=200, blank=True,
        default="Cuentas premium oficiales: Netflix, Disney+, Spotify, Office y más. Pago Yape o Mercado Pago. Garantía 30 días.",
    )

    # Tracking & analytics
    ga4_measurement_id = models.CharField(
        "GA4 Measurement ID", max_length=20, blank=True,
        help_text="Ej: G-XXXXXXXXXX (de Google Analytics 4 → Admin → Streams).",
    )
    meta_pixel_id = models.CharField(
        "Meta Pixel ID", max_length=20, blank=True,
        help_text="Ej: 1234567890123456 (de Meta Business → Eventos → Pixels).",
    )
    google_ads_id = models.CharField(
        "Google Ads Conversion ID", max_length=30, blank=True,
        help_text="Ej: AW-123456789 (opcional, para Google Ads).",
    )
    tiktok_pixel_id = models.CharField(
        "TikTok Pixel ID", max_length=30, blank=True,
        help_text="Opcional, para retargeting en TikTok.",
    )

    # Operacional
    maintenance_mode = models.BooleanField(
        "Modo mantenimiento", default=False,
        help_text="Si está activo, se muestra una página de mantenimiento en lugar del sitio normal.",
    )
    maintenance_message = models.TextField(
        "Mensaje de mantenimiento", blank=True,
        default="Volvemos en unos minutos. ¡Disculpa las molestias!",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración del sitio"
        verbose_name_plural = "Configuración del sitio"

    def __str__(self) -> str:
        return "Configuración del sitio"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        try:
            from django.core.cache import cache
            cache.delete("jh_tracking_ids")
        except Exception:
            pass

    @classmethod
    def load(cls) -> "SiteSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def whatsapp_link(self) -> str:
        """Link wa.me con número y mensaje pre-rellenado."""
        from urllib.parse import quote
        if not self.whatsapp_number:
            return ""
        msg = quote(self.whatsapp_message or "")
        return f"https://wa.me/{self.whatsapp_number}?text={msg}"


class Reclamacion(models.Model):
    """Libro de Reclamaciones digital obligatorio por Indecopi (D.S. 011-2011-PCM).

    Cada entrada queda inmutable, con número correlativo automático y fecha.
    El proveedor tiene 30 días calendario para responder. El cliente recibe
    copia por email y nosotros vemos el listado en el admin.
    """

    class TipoBien(models.TextChoices):
        PRODUCTO = "producto", "Producto"
        SERVICIO = "servicio", "Servicio"

    class TipoReclamo(models.TextChoices):
        RECLAMO = "reclamo", "Reclamo (disconformidad con producto/servicio)"
        QUEJA = "queja", "Queja (disconformidad con la atención)"

    class Estado(models.TextChoices):
        RECIBIDO = "recibido", "Recibido"
        EN_REVISION = "en_revision", "En revisión"
        RESPONDIDO = "respondido", "Respondido"
        CERRADO = "cerrado", "Cerrado"

    # Correlativo único (formato: AAAA-NNNN)
    numero = models.CharField(
        "Número de reclamación", max_length=20, unique=True, blank=True,
    )

    # Datos del consumidor (Indecopi obliga a estos)
    nombre = models.CharField("Nombre completo", max_length=160)
    documento_tipo = models.CharField(
        "Tipo de documento", max_length=10, default="DNI",
        choices=(("DNI", "DNI"), ("CE", "Carné de extranjería"), ("PAS", "Pasaporte")),
    )
    documento_numero = models.CharField("Número de documento", max_length=20)
    domicilio = models.CharField("Domicilio", max_length=200, blank=True)
    telefono = models.CharField("Teléfono", max_length=30)
    email = models.EmailField("Correo electrónico")

    # Si es menor de edad
    es_menor = models.BooleanField("Soy menor de edad", default=False)
    padre_nombre = models.CharField(
        "Nombre del padre / madre / representante", max_length=160, blank=True,
    )
    padre_documento = models.CharField(
        "Documento del representante", max_length=20, blank=True,
    )

    # Datos del bien contratado
    tipo_bien = models.CharField(
        "Tipo de bien", max_length=10, choices=TipoBien.choices,
        default=TipoBien.PRODUCTO,
    )
    monto = models.DecimalField(
        "Monto reclamado (S/)", max_digits=10, decimal_places=2,
        null=True, blank=True,
    )
    descripcion_bien = models.CharField(
        "Descripción del producto / servicio", max_length=300,
    )
    pedido_referencia = models.CharField(
        "N° de pedido (si aplica)", max_length=50, blank=True,
    )

    # Detalle del reclamo
    tipo = models.CharField(
        "Tipo", max_length=10, choices=TipoReclamo.choices,
    )
    detalle = models.TextField("Detalle del reclamo / queja")
    pedido_consumidor = models.TextField(
        "Pedido del consumidor",
        help_text="¿Qué solicita el consumidor para resolver el caso?",
    )

    # Estado interno (admin)
    estado = models.CharField(
        "Estado", max_length=20, choices=Estado.choices,
        default=Estado.RECIBIDO,
    )
    respuesta = models.TextField("Respuesta del proveedor", blank=True)
    respondido_en = models.DateTimeField("Fecha de respuesta", null=True, blank=True)

    # Auditoría
    ip_address = models.GenericIPAddressField("IP del cliente", null=True, blank=True)
    user_agent = models.CharField("User agent", max_length=300, blank=True)
    created_at = models.DateTimeField("Fecha de presentación", auto_now_add=True)

    class Meta:
        verbose_name = "Reclamación (Libro Indecopi)"
        verbose_name_plural = "Libro de Reclamaciones (Indecopi)"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.numero} — {self.nombre}"

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            year = timezone.now().year
            last = (
                Reclamacion.objects
                .filter(numero__startswith=f"{year}-")
                .order_by("-numero")
                .first()
            )
            if last and last.numero:
                try:
                    n = int(last.numero.split("-")[1]) + 1
                except (ValueError, IndexError):
                    n = 1
            else:
                n = 1
            self.numero = f"{year}-{n:04d}"
        super().save(*args, **kwargs)

    @property
    def vence_at(self):
        """Fecha límite de respuesta (30 días calendario por Indecopi)."""
        from datetime import timedelta
        return self.created_at + timedelta(days=30)

    @property
    def dias_restantes(self) -> int:
        from django.utils import timezone
        return max(0, (self.vence_at.date() - timezone.localdate()).days)
