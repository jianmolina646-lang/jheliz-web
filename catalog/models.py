from decimal import Decimal

from django.db import models
from django.urls import reverse
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

    def price_for(self, user) -> Decimal | None:
        """Precio m\u00ednimo visible para el usuario actual."""
        plans = self.active_plans(user).order_by("price_customer")
        plan = plans.first()
        if not plan:
            return None
        return plan.price_for(user)

    def active_plans(self, user=None):
        qs = self.plans.filter(is_active=True)
        if user and getattr(user, "is_distributor", False):
            return qs
        return qs.filter(available_for_customer=True)

    @property
    def available_stock(self) -> int:
        return sum(p.available_stock for p in self.plans.all())


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


class StockItem(models.Model):
    """Una credencial concreta lista para entregar."""

    class Status(models.TextChoices):
        AVAILABLE = "available", "Disponible"
        RESERVED = "reserved", "Reservada"
        SOLD = "sold", "Vendida"
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

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Stock"
        verbose_name_plural = "Stock"
        indexes = [
            models.Index(fields=["product", "status"]),
            models.Index(fields=["plan", "status"]),
        ]

    def __str__(self) -> str:
        plan = self.plan.name if self.plan else "cualquier plan"
        return f"{self.product.name} \u2014 {plan} \u2014 {self.get_status_display()}"
