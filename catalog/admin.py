from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from .models import (
    Category,
    CustomerPlan,
    DistributorPlan,
    Plan,
    Product,
    StockItem,
    Testimonial,
)


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ("name", "emoji", "audience", "order", "is_active")
    list_editable = ("order", "is_active")
    list_filter = ("audience", "is_active")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


class PlanInline(TabularInline):
    model = Plan
    extra = 1
    fields = (
        "name", "duration_days", "price_customer", "price_distributor",
        "available_for_customer", "available_for_distributor", "is_active", "order",
    )


@admin.register(Plan)
class PlanAdmin(ModelAdmin):
    """Listado completo (cliente + distribuidor)."""
    list_display = ("product", "name", "duration_days", "price_customer", "price_distributor", "is_active")
    list_filter = ("is_active", "available_for_customer", "available_for_distributor")
    search_fields = ("product__name", "name")
    autocomplete_fields = ("product",)


@admin.register(CustomerPlan)
class CustomerPlanAdmin(ModelAdmin):
    """Vista enfocada en cliente final: solo se ve y edita el precio cliente."""
    list_display = ("product", "name", "duration_days", "price_customer", "available_stock_short", "is_active")
    list_filter = ("is_active", "product__category")
    search_fields = ("product__name", "name")
    autocomplete_fields = ("product",)
    fieldsets = (
        (None, {"fields": ("product", "name", "duration_days")}),
        ("Precio cliente final", {"fields": ("price_customer", "available_for_customer")}),
        ("Avanzado", {
            "classes": ("collapse",),
            "fields": ("is_active", "order", "low_stock_threshold"),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).filter(available_for_customer=True)

    def save_model(self, request, obj, form, change):
        # Forzar visibilidad cliente en esta sección.
        obj.available_for_customer = True
        super().save_model(request, obj, form, change)

    @display(description="Stock", ordering="-id")
    def available_stock_short(self, obj):
        return obj.available_stock


@admin.register(DistributorPlan)
class DistributorPlanAdmin(ModelAdmin):
    """Vista mayorista: solo se ve y edita el precio distribuidor."""
    list_display = ("product", "name", "duration_days", "price_distributor", "available_stock_short", "is_active")
    list_filter = ("is_active", "product__category")
    search_fields = ("product__name", "name")
    autocomplete_fields = ("product",)
    fieldsets = (
        (None, {"fields": ("product", "name", "duration_days")}),
        ("Precio distribuidor (mayorista)", {"fields": ("price_distributor", "available_for_distributor")}),
        ("Avanzado", {
            "classes": ("collapse",),
            "fields": ("is_active", "order", "low_stock_threshold"),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).filter(available_for_distributor=True)

    def save_model(self, request, obj, form, change):
        obj.available_for_distributor = True
        super().save_model(request, obj, form, change)

    @display(description="Stock", ordering="-id")
    def available_stock_short(self, obj):
        return obj.available_stock


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = (
        "product_preview", "category", "mode", "display_active",
        "is_featured", "delivery_is_instant", "available_stock_count",
    )
    list_filter = ("category", "mode", "is_active", "is_featured")
    search_fields = ("name", "short_description")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [PlanInline]
    list_filter_submit = True
    compressed_fields = True

    @display(description="Producto", ordering="name")
    def product_preview(self, obj: Product) -> str:
        emoji = obj.icon or obj.category.emoji or ""
        return format_html(
            '<div class="flex items-center gap-2">'
            '<span class="text-2xl">{}</span>'
            '<span class="font-medium">{}</span>'
            '</div>',
            emoji, obj.name,
        )

    @display(
        description="Visible",
        boolean=True,
        ordering="is_active",
    )
    def display_active(self, obj: Product) -> bool:
        return obj.is_active

    def available_stock_count(self, obj: Product) -> int:
        return obj.available_stock
    available_stock_count.short_description = "Stock disp."


class StockImportForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.all(), label="Producto",
    )
    plan = forms.ModelChoiceField(
        queryset=Plan.objects.all(), required=False, label="Plan (opcional)",
        help_text="Si lo dejas en blanco, el stock servir\u00e1 para cualquier plan del producto.",
    )
    file = forms.FileField(
        label="Archivo .txt / .csv",
        required=False,
        help_text="Sube un archivo, o pega el contenido en el cuadro de abajo.",
    )
    pasted = forms.CharField(
        label="O pega aquí (Excel, Sheets, .csv, .txt)",
        required=False,
        widget=forms.Textarea(attrs={
            "rows": 12,
            "style": "font-family:Menlo,Consolas,monospace;font-size:13px;width:100%;",
            "placeholder": (
                "Acepta varios formatos:\n\n"
                "1) CSV con cabecera (separador ',' o ';' o tab):\n"
                "   email,password,perfil,pin\n"
                "   user1@gmail.com,Abc123,Perfil 1,1234\n"
                "   user2@gmail.com,Xyz789,Perfil 2,5678\n\n"
                "2) Una línea por cuenta (sin cabecera): correo|clave|perfil|pin\n\n"
                "3) Bloques separados por línea en blanco (texto libre)."
            ),
        }),
    )

    def clean(self) -> dict:
        cleaned = super().clean()
        if not cleaned.get("file") and not (cleaned.get("pasted") or "").strip():
            raise forms.ValidationError(
                "Sube un archivo o pega contenido en el cuadro de texto."
            )
        return cleaned


@admin.register(StockItem)
class StockItemAdmin(ModelAdmin):
    list_display = ("product", "plan", "status", "label", "created_at", "sold_at")
    list_filter = ("status", "product", "plan")
    search_fields = ("product__name", "label", "credentials")
    autocomplete_fields = ("product", "plan")
    readonly_fields = ("created_at", "sold_at")
    change_list_template = "admin/catalog/stock_changelist.html"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "importar/",
                self.admin_site.admin_view(self.import_view),
                name="catalog_stockitem_import",
            ),
        ]
        return custom + urls

    def import_view(self, request):
        if request.method == "POST":
            form = StockImportForm(request.POST, request.FILES)
            if form.is_valid():
                if form.cleaned_data.get("file"):
                    content = form.cleaned_data["file"].read().decode(
                        "utf-8", errors="replace"
                    )
                else:
                    content = form.cleaned_data["pasted"]
                created = self._process_file(
                    content,
                    product=form.cleaned_data["product"],
                    plan=form.cleaned_data["plan"],
                )
                messages.success(
                    request,
                    f"Se importaron {created} entradas de stock para "
                    f"{form.cleaned_data['product'].name}.",
                )
                return redirect(reverse("admin:catalog_stockitem_changelist"))
        else:
            form = StockImportForm()
        return render(
            request,
            "admin/catalog/stock_import.html",
            {
                "form": form,
                "title": "Importar stock — masivo",
                "opts": StockItem._meta,
            },
        )

    def _process_file(self, content: str, product: Product, plan: Plan | None) -> int:
        """Importa stock soportando 3 formatos:

        1. CSV/TSV con cabecera (separador autodetectado: ``,``, ``;`` o tab).
           Cabeceras esperadas (case-insensitive, acentos opcionales):
           ``email``/``correo``, ``password``/``contraseña``/``clave``,
           ``profile``/``perfil``, ``pin``, ``label``/``etiqueta``.
        2. Una línea por cuenta sin cabecera, separadas por ``|``:
           ``correo|clave|perfil|pin``.
        3. Bloques de texto libre separados por línea en blanco.
        """
        import csv
        import io

        content = content.strip()
        if not content:
            return 0
        lines = content.splitlines()
        non_empty = [l for l in lines if l.strip()]

        # Formato 1: CSV/TSV con cabecera. Lo detectamos si la primera línea
        # tiene cabecera reconocible (email/correo) y separadores , ; o tab.
        first = non_empty[0].lower() if non_empty else ""
        is_csv_like = (
            ("email" in first or "correo" in first)
            and any(sep in first for sep in (",", ";", "\t"))
        )
        if is_csv_like:
            return self._import_csv(content, product, plan)

        # Formato 2: pipe-separated, una por línea.
        if all("|" in line for line in non_empty):
            return self._import_pipe(non_empty, product, plan)

        # Formato 3: bloques.
        return self._import_blocks(content, product, plan)

    def _import_csv(self, content: str, product: Product, plan: Plan | None) -> int:
        import csv
        import io

        # Autodetectar separador.
        sample = content[:2048]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(content), dialect=dialect)
        # Normalizar cabeceras: minúsculas y sin tildes.
        def norm(s: str) -> str:
            s = (s or "").strip().lower()
            return (
                s.replace("á", "a").replace("é", "e").replace("í", "i")
                .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
            )

        if not reader.fieldnames:
            return 0
        original = list(reader.fieldnames)
        reader.fieldnames = [norm(h) for h in original]
        # Mapeo de cabecera real → nombre canónico.
        canon = {
            "email": "email", "correo": "email", "usuario": "email", "user": "email",
            "password": "password", "contrasena": "password", "clave": "password", "pass": "password",
            "profile": "profile", "perfil": "profile",
            "pin": "pin",
            "label": "label", "etiqueta": "label",
        }
        created = 0
        for row in reader:
            data = {canon.get(k, k): (v or "").strip() for k, v in row.items() if k}
            email = data.get("email", "")
            password = data.get("password", "")
            if not email or not password:
                continue
            creds = f"Correo: {email}\nContraseña: {password}"
            if data.get("profile"):
                creds += f"\nPerfil: {data['profile']}"
            if data.get("pin"):
                creds += f"\nPIN: {data['pin']}"
            StockItem.objects.create(
                product=product, plan=plan,
                credentials=creds, label=data.get("label", "")[:80],
            )
            created += 1
        return created

    def _import_pipe(self, lines: list[str], product: Product, plan: Plan | None) -> int:
        created = 0
        for line in lines:
            parts = [p.strip() for p in line.strip().split("|")]
            if len(parts) < 2:
                continue
            email, password, *rest = parts
            creds = f"Correo: {email}\nContraseña: {password}"
            if rest:
                perfil = rest[0] if len(rest) > 0 else ""
                pin = rest[1] if len(rest) > 1 else ""
                if perfil:
                    creds += f"\nPerfil: {perfil}"
                if pin:
                    creds += f"\nPIN: {pin}"
            StockItem.objects.create(
                product=product, plan=plan, credentials=creds,
            )
            created += 1
        return created

    def _import_blocks(self, content: str, product: Product, plan: Plan | None) -> int:
        created = 0
        blocks = [b.strip() for b in content.split("\n\n") if b.strip()]
        for block in blocks:
            StockItem.objects.create(
                product=product, plan=plan, credentials=block,
            )
            created += 1
        return created


@admin.register(Testimonial)
class TestimonialAdmin(ModelAdmin):
    list_display = ("author", "city", "rating", "is_published", "order", "created_at")
    list_filter = ("is_published", "rating", "city")
    search_fields = ("author", "text", "city")
    list_editable = ("is_published", "order")
    ordering = ("order", "-created_at")
    fieldsets = (
        (None, {"fields": ("author", "city", "rating", "text", "product")}),
        ("Publicación", {"fields": ("is_published", "order")}),
    )
