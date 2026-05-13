from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import escape, format_html
from django.utils.safestring import SafeString
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action as unfold_action, display

from accounts.admin_helpers import chip
from .models import (
    BackInStockAlert,
    Category,
    CustomerPlan,
    DistributorPlan,
    Plan,
    PlatformLanding,
    Product,
    ProductReview,
    PromoBanner,
    Reclamacion,
    SiteSettings,
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


class _PlanDisplayMixin:
    """Helpers comunes para los 3 admins de Plan: render con chips.

    Da una experiencia uniforme al listar planes (general, cliente,
    distribuidor): la celda del producto trae ícono/imagen, la duración
    y el precio se muestran como chips compactos con tonos semafóricos,
    y el estado activo se muestra como pill ("Activo" / "Inactivo").
    """

    @display(description="Producto", ordering="product__name")
    def plan_product_cell(self, obj) -> SafeString:
        product = obj.product
        emoji = (
            product.icon
            or (product.category.emoji if product.category_id else "")
            or "\U0001F3AC"
        )
        sub = f"{product.category.name if product.category_id else ''} · {obj.name}"
        if product.image:
            return format_html(
                '<div class="jh-product-cell">'
                '<img class="jh-product-cell__img" src="{}" alt="" loading="lazy" />'
                '<div class="jh-product-cell__txt">'
                '<div class="jh-product-cell__name">{}</div>'
                '<div class="jh-product-cell__sub">{}</div>'
                '</div></div>',
                product.image.url, product.name, sub,
            )
        return format_html(
            '<div class="jh-product-cell">'
            '<span class="jh-product-cell__emoji">{}</span>'
            '<div class="jh-product-cell__txt">'
            '<div class="jh-product-cell__name">{}</div>'
            '<div class="jh-product-cell__sub">{}</div>'
            '</div></div>',
            emoji, product.name, sub,
        )

    @display(description="Duración", ordering="duration_days")
    def plan_duration_chip(self, obj) -> SafeString:
        if not obj.duration_days:
            return chip("Perpetua", tone="violet", icon="all_inclusive")
        d = obj.duration_days
        if d >= 365:
            label = f"{d // 365} año{'s' if d // 365 != 1 else ''}"
        elif d >= 30:
            months = d // 30
            label = f"{months} mes{'es' if months != 1 else ''}"
        else:
            label = f"{d} día{'s' if d != 1 else ''}"
        return chip(label, tone="info", icon="schedule")

    @display(description="Precio cliente", ordering="price_customer")
    def plan_price_customer_chip(self, obj) -> SafeString:
        from decimal import Decimal
        if obj.price_customer is None or obj.price_customer <= Decimal("0"):
            return chip("Sin precio", tone="neutral", icon="block")
        return chip(f"S/ {obj.price_customer:.2f}", tone="success", icon="payments")

    @display(description="Precio distri", ordering="price_distributor")
    def plan_price_distributor_chip(self, obj) -> SafeString:
        from decimal import Decimal
        if obj.price_distributor is None or obj.price_distributor <= Decimal("0"):
            return chip("Sin precio", tone="neutral", icon="block")
        return chip(f"S/ {obj.price_distributor:.2f}", tone="violet", icon="storefront")

    @display(description="Stock", ordering="-id")
    def plan_stock_chip(self, obj) -> SafeString:
        stock = obj.available_stock
        threshold = obj.low_stock_threshold or 3
        if stock == 0:
            tone, icon = "danger", "remove_shopping_cart"
        elif stock <= threshold:
            tone, icon = "warning", "warning"
        else:
            tone, icon = "success", "inventory_2"
        return chip(str(stock), tone=tone, icon=icon)

    @display(description="Estado", ordering="is_active")
    def plan_active_chip(self, obj) -> SafeString:
        if obj.is_active:
            return chip("Activo", tone="success", icon="check_circle")
        return chip("Inactivo", tone="neutral", icon="pause_circle")


@admin.register(Plan)
class PlanAdmin(_PlanDisplayMixin, ModelAdmin):
    """Listado completo (cliente + distribuidor)."""
    list_display = (
        "plan_product_cell", "plan_duration_chip",
        "plan_price_customer_chip", "plan_price_distributor_chip",
        "plan_stock_chip", "plan_active_chip",
    )
    list_filter = ("is_active", "available_for_customer", "available_for_distributor")
    search_fields = ("product__name", "name")
    autocomplete_fields = ("product",)


@admin.register(CustomerPlan)
class CustomerPlanAdmin(_PlanDisplayMixin, ModelAdmin):
    """Vista enfocada en cliente final: solo se ve y edita el precio cliente."""
    list_display = (
        "plan_product_cell", "plan_duration_chip",
        "plan_price_customer_chip", "plan_stock_chip", "plan_active_chip",
    )
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


@admin.register(DistributorPlan)
class DistributorPlanAdmin(_PlanDisplayMixin, ModelAdmin):
    """Vista mayorista: solo se ve y edita el precio distribuidor."""
    list_display = (
        "plan_product_cell", "plan_duration_chip",
        "plan_price_distributor_chip", "plan_stock_chip", "plan_active_chip",
    )
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


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = (
        "product_preview", "mode_badge", "available_stock_count",
        "display_active", "featured_badge", "telegram_badge", "delivery_badge",
    )
    list_filter = ("category", "mode", "is_active", "is_featured", "telegram_audience")
    search_fields = ("name", "short_description")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [PlanInline]
    list_filter_submit = True
    compressed_fields = True
    # Drag & drop en el changelist usando el campo `order` (#11).
    ordering_field = "order"
    hide_ordering_field = True
    actions = (
        "action_announce_default",
        "action_announce_to_customers",
        "action_announce_to_distributors",
        "action_announce_to_both",
        "action_activate", "action_deactivate",
        "action_mark_featured", "action_unmark_featured",
    )
    # Botones que aparecen arriba del formulario de edición de un producto.
    # Ofrecen postear ese producto puntual a Telegram con un solo toque.
    actions_detail = (
        "detail_publish_to_customers",
        "detail_publish_to_distributors",
        "detail_publish_to_both",
    )

    def _publish_single(self, request, object_id, audience, label):
        """Publica UN producto puntual al canal indicado y vuelve al admin."""
        from orders import telegram

        product = self.get_object(request, object_id)
        if product is None:
            self.message_user(request, "Producto no encontrado.", level=messages.ERROR)
            return redirect(reverse("admin:catalog_product_changelist"))

        if not telegram.is_configured():
            self.message_user(
                request,
                "TELEGRAM_BOT_TOKEN no configurado — no se publicó nada.",
                level=messages.WARNING,
            )
            return redirect(
                reverse("admin:catalog_product_change", args=[object_id]),
            )

        if not telegram.channel_is_configured(audience):
            self.message_user(
                request,
                f"Canal '{label}' sin configurar en .env — no se publicó nada.",
                level=messages.WARNING,
            )
            return redirect(
                reverse("admin:catalog_product_change", args=[object_id]),
            )

        res = telegram.announce_product(product, kind="new", audience=audience)
        if res and res.get("ok"):
            self.message_user(
                request,
                f"📢 Publicado en Telegram → canal {label} ({product.name}).",
                level=messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                f"❌ No se pudo publicar en canal {label}: {res}",
                level=messages.ERROR,
            )
        return redirect(reverse("admin:catalog_product_change", args=[object_id]))

    @unfold_action(
        description="📢 Publicar en Telegram · 🛍 Clientes",
        url_path="publish-telegram-customer",
    )
    def detail_publish_to_customers(self, request, object_id):
        from orders import telegram
        return self._publish_single(
            request, object_id, telegram.AUDIENCE_CUSTOMER, "clientes",
        )

    @unfold_action(
        description="📢 Publicar en Telegram · 🏪 Distribuidores",
        url_path="publish-telegram-distrib",
    )
    def detail_publish_to_distributors(self, request, object_id):
        from orders import telegram
        return self._publish_single(
            request, object_id, telegram.AUDIENCE_DISTRIB, "distribuidores",
        )

    @unfold_action(
        description="📢 Publicar en Telegram · 🌐 Ambos canales",
        url_path="publish-telegram-both",
    )
    def detail_publish_to_both(self, request, object_id):
        from orders import telegram
        return self._publish_single(
            request, object_id, telegram.AUDIENCE_ALL, "ambos canales",
        )

    @admin.action(description="✓ Activar (visible en tienda)")
    def action_activate(self, request, queryset):
        n = queryset.update(is_active=True)
        self.message_user(request, f"{n} producto(s) activado(s).")

    @admin.action(description="⏸ Desactivar (oculto en tienda)")
    def action_deactivate(self, request, queryset):
        n = queryset.update(is_active=False)
        self.message_user(request, f"{n} producto(s) desactivado(s).")

    @admin.action(description="⭐ Destacar en home")
    def action_mark_featured(self, request, queryset):
        n = queryset.update(is_featured=True)
        self.message_user(request, f"{n} producto(s) destacado(s) en home.")

    @admin.action(description="☆ Quitar de destacados")
    def action_unmark_featured(self, request, queryset):
        n = queryset.update(is_featured=False)
        self.message_user(request, f"{n} producto(s) sin destacar.")

    def _run_announce(self, request, queryset, audience, label):
        from orders import telegram

        if audience and not telegram.channel_is_configured(audience):
            self.message_user(
                request,
                f"Canal ({label}) sin configurar en .env — no se publicó nada.",
                level=messages.WARNING,
            )
            return
        ok = 0
        fail = 0
        skipped = 0
        for product in queryset:
            if audience is None:
                # Usa la configuración del producto (campo telegram_audience).
                if product.telegram_audience == "none":
                    skipped += 1
                    continue
                res = telegram.announce_product(product, kind="new")
            else:
                res = telegram.announce_product(product, kind="new", audience=audience)
            if res and res.get("ok"):
                ok += 1
            else:
                fail += 1
        level = messages.SUCCESS if fail == 0 else messages.WARNING
        msg = f"Publicación al canal ({label}): {ok} ok · {fail} con error"
        if skipped:
            msg += f" · {skipped} omitidos (configurados 'No publicar')"
        self.message_user(request, msg + ".", level=level)

    @admin.action(description="📣 Publicar según config del producto")
    def action_announce_default(self, request, queryset):
        self._run_announce(request, queryset, audience=None, label="según producto")

    @admin.action(description="📣 Publicar SOLO al canal de clientes")
    def action_announce_to_customers(self, request, queryset):
        from orders import telegram
        self._run_announce(request, queryset, audience=telegram.AUDIENCE_CUSTOMER, label="clientes")

    @admin.action(description="📣 Publicar SOLO al canal de distribuidores")
    def action_announce_to_distributors(self, request, queryset):
        from orders import telegram
        self._run_announce(request, queryset, audience=telegram.AUDIENCE_DISTRIB, label="distribuidores")

    @admin.action(description="📣 Publicar a AMBOS canales")
    def action_announce_to_both(self, request, queryset):
        from orders import telegram
        self._run_announce(request, queryset, audience=telegram.AUDIENCE_ALL, label="ambos")

    @display(description="Producto", ordering="name")
    def product_preview(self, obj: Product) -> str:
        emoji = obj.icon or (obj.category.emoji if obj.category_id else "") or "\U0001F3AC"
        if obj.image:
            return format_html(
                '<div class="jh-product-cell">'
                '<img class="jh-product-cell__img" src="{}" alt="" loading="lazy" />'
                '<div class="jh-product-cell__txt">'
                '<div class="jh-product-cell__name">{}</div>'
                '<div class="jh-product-cell__sub">{}</div>'
                '</div></div>',
                obj.image.url,
                obj.name,
                obj.category.name if obj.category_id else "",
            )
        return format_html(
            '<div class="jh-product-cell">'
            '<span class="jh-product-cell__emoji">{}</span>'
            '<div class="jh-product-cell__txt">'
            '<div class="jh-product-cell__name">{}</div>'
            '<div class="jh-product-cell__sub">{}</div>'
            '</div></div>',
            emoji, obj.name,
            obj.category.name if obj.category_id else "",
        )

    @display(
        description="Visible",
        boolean=True,
        ordering="is_active",
    )
    def display_active(self, obj: Product) -> bool:
        return obj.is_active

    def available_stock_count(self, obj: Product) -> SafeString:
        n = obj.available_stock
        if n == 0:
            tone = "danger"
        elif n < 3:
            tone = "warning"
        else:
            tone = "success"
        return chip(str(n), tone=tone, icon="inventory_2")
    available_stock_count.short_description = "Stock"

    @display(description="Modo", ordering="mode")
    def mode_badge(self, obj: Product) -> SafeString:
        """Pill compacta con ícono según el modo de venta del producto."""
        mapping = {
            "perfil": ("success", "person", "Por perfil"),
            "completa": ("violet", "vpn_key", "Completa"),
            "licencia": ("warning", "card_membership", "Licencia"),
        }
        tone, icon, label = mapping.get(
            obj.mode, ("neutral", "category", obj.get_mode_display() or "—"),
        )
        return chip(label, tone=tone, icon=icon)

    @display(description="Destacado", ordering="is_featured")
    def featured_badge(self, obj: Product) -> SafeString:
        if obj.is_featured:
            return chip("Sí", tone="warning", icon="star")
        return chip("No", tone="neutral", icon="star_outline")

    @display(description="Telegram", ordering="telegram_audience")
    def telegram_badge(self, obj: Product) -> SafeString:
        mapping = {
            "both":        ("violet",  "public",      "Ambos"),
            "customer":    ("success", "shopping_bag","Clientes"),
            "distributor": ("info",    "storefront",  "Distri"),
            "none":        ("neutral", "block",       "No publicar"),
        }
        tone, icon, label = mapping.get(
            obj.telegram_audience,
            ("neutral", "help", obj.get_telegram_audience_display() or "—"),
        )
        return chip(label, tone=tone, icon=icon)

    @display(description="Entrega", ordering="delivery_is_instant")
    def delivery_badge(self, obj: Product) -> SafeString:
        if obj.delivery_is_instant:
            return chip("Inmediata", tone="success", icon="bolt")
        return chip("Manual", tone="neutral", icon="pan_tool")


_INPUT_CLS = (
    "w-full rounded-md bg-base-950 border border-base-700 text-white text-sm "
    "px-3 py-2 focus:border-primary-500 focus:outline-none"
)


class StockImportForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.all(), label="Producto",
        widget=forms.Select(attrs={"class": _INPUT_CLS}),
    )
    plan = forms.ModelChoiceField(
        queryset=Plan.objects.all(), required=False, label="Plan (opcional)",
        help_text="Si lo dejas en blanco, el stock servir\u00e1 para cualquier plan del producto.",
        widget=forms.Select(attrs={"class": _INPUT_CLS}),
    )
    file = forms.FileField(
        label="Archivo .txt / .csv",
        required=False,
        help_text="Sube un archivo, o pega el contenido en el cuadro de abajo.",
        widget=forms.ClearableFileInput(attrs={"class": _INPUT_CLS + " file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:bg-primary-500 file:text-white"}),
    )
    pasted = forms.CharField(
        label="O pega aquí (Excel, Sheets, .csv, .txt)",
        required=False,
        widget=forms.Textarea(attrs={
            "rows": 12,
            "class": _INPUT_CLS + " font-mono resize-y",
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
    list_display = (
        "product", "plan", "status_badge", "status", "label",
        "created_at", "sold_at", "provider_expires_at",
    )
    list_editable = ("status", "label")
    list_filter = ("status", "product", "plan", "provider_expires_at")
    search_fields = ("product__name", "label", "credentials")
    autocomplete_fields = ("product", "plan")
    # `sold_at` queda editable para arreglar manualmente fechas históricas
    # de stocks marcados como vendidos sin pasar por el flujo normal.
    # El sistema lo setea automáticamente cuando el flujo de entrega
    # marca un stock como SOLD; este override es para casos puntuales.
    readonly_fields = ("created_at",)
    change_list_template = "admin/catalog/stock_changelist.html"
    actions = ("action_mark_defective", "action_mark_available", "action_duplicate")

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

    def save_model(self, request, obj, form, change):
        # Si el admin marca un stock como Vendida (manual o reconciliando
        # ventas históricas) y no había `sold_at`, lo seteamos automáticamente
        # con el timestamp actual para que aparezca en filtros por fecha.
        if obj.status == StockItem.Status.SOLD and obj.sold_at is None:
            from django.utils import timezone

            obj.sold_at = timezone.now()
        super().save_model(request, obj, form, change)

    def status_badge(self, obj):
        tones = {
            "available": ("success", "check_circle"),
            "reserved": ("neutral", "radio_button_checked"),
            "sold": ("info", "shopping_cart_checkout"),
            "defective": ("danger", "warning"),
            "disabled": ("neutral", "block"),
        }
        tone, icon = tones.get(obj.status, ("neutral", None))
        return chip(obj.get_status_display(), tone=tone, icon=icon)

    status_badge.short_description = "Estado"
    status_badge.admin_order_field = "status"

    def action_mark_defective(self, request, queryset):
        # Cuando se cae una cuenta, marcarla como DEFECTIVE y desvincular
        # los OrderItems que la tenían linkeada (RESERVED) para que el
        # admin pueda recargar stock fresco. Los SOLD se mantienen
        # vinculados a fines históricos pero igual el ítem queda con la
        # cuenta caída.
        affected_orders: list[str] = []
        n = 0
        for item in queryset:
            previous_status = item.status
            item.status = StockItem.Status.DEFECTIVE
            item.save(update_fields=["status"])
            # Avisar de pedidos que dependían de este stock para que el
            # admin sepa qué tiene que rotar. SOLD queda intacto: es
            # parte del historial y el cliente ya recibió la cuenta.
            if previous_status in {
                StockItem.Status.AVAILABLE,
                StockItem.Status.RESERVED,
            }:
                from orders.models import OrderItem

                linked = list(
                    OrderItem.objects.filter(stock_item=item)
                    .select_related("order")
                )
                for oi in linked:
                    affected_orders.append(
                        f"#{oi.order.short_uuid} ({oi.product_name})"
                    )
                # Desvincular para que el flujo de reserva pueda asignar
                # otro stock disponible si lo hay.
                OrderItem.objects.filter(stock_item=item).update(stock_item=None)
            n += 1
        msg = f"{n} stock marcado como caída/reportada."
        if affected_orders:
            msg += (
                f" Pedidos que tenían esta cuenta y quedaron sin stock: "
                f"{', '.join(affected_orders)}."
            )
        self.message_user(request, msg)

    action_mark_defective.short_description = "⚠ Marcar como caída/reportada"

    def action_mark_available(self, request, queryset):
        # Reactivar: vuelve a Disponible. Si venía de SOLD (reactivamos
        # una cuenta que se había marcado vendida por error o que ya
        # podemos reusar), limpiamos `sold_at` para no contaminar
        # filtros y reportes históricos.
        n = queryset.update(
            status=StockItem.Status.AVAILABLE,
            sold_at=None,
        )
        self.message_user(request, f"{n} stock marcado como disponible.")

    action_mark_available.short_description = "✓ Marcar como disponible"

    def action_duplicate(self, request, queryset):
        created = 0
        for item in queryset:
            StockItem.objects.create(
                product=item.product,
                plan=item.plan,
                credentials=item.credentials,
                label=item.label,
                status=StockItem.Status.AVAILABLE,
            )
            created += 1
        self.message_user(request, f"{created} stock(s) duplicado(s) como disponibles.")

    action_duplicate.short_description = "🔁 Duplicar (clonar)"

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
                created, skipped = self._process_file_with_stats(
                    content,
                    product=form.cleaned_data["product"],
                    plan=form.cleaned_data["plan"],
                )
                msg = (
                    f"Se importaron {created} entradas de stock para "
                    f"{form.cleaned_data['product'].name}."
                )
                if skipped:
                    msg += (
                        f" Se omitieron {skipped} duplicado(s) "
                        "(email ya existía en el stock)."
                    )
                messages.success(request, msg)
                return redirect(reverse("admin:catalog_stockitem_changelist"))
        else:
            initial = {}
            preselected_pk = request.GET.get("product")
            if preselected_pk:
                try:
                    initial["product"] = Product.objects.get(pk=int(preselected_pk))
                except (ValueError, Product.DoesNotExist):
                    pass
            form = StockImportForm(initial=initial)
        from config.admin_views import stock_module_kpis

        return render(
            request,
            "admin/catalog/stock_import.html",
            {
                **self.admin_site.each_context(request),
                "form": form,
                "title": "Stock — Importar",
                "opts": StockItem._meta,
                "stock_kpis": stock_module_kpis(),
                "active_tab": "importar",
            },
        )

    def _process_file(self, content: str, product: Product, plan: Plan | None) -> int:
        """Wrapper retro-compat: devuelve solo el número de creados."""
        created, _skipped = self._process_file_with_stats(content, product, plan)
        return created

    def _process_file_with_stats(
        self, content: str, product: Product, plan: Plan | None
    ) -> tuple[int, int]:
        """Importa stock soportando varios formatos.

        Devuelve ``(created, skipped_duplicates)``. Detecta duplicados por
        cuenta dentro del mismo producto: para stock compartido permite el
        mismo correo si cambia el perfil, pero evita repetir la misma
        combinación correo+perfil (o una cuenta genérica sin perfil).

        Formatos soportados:
        1. CSV/TSV con cabecera (separador autodetectado: ``,``, ``;`` o tab).
           Cabeceras esperadas: ``email``/``correo``, ``password``/``clave``,
           ``profile``/``perfil``, ``pin``, ``label``/``etiqueta``.
        2. Una línea por cuenta separada por ``|``, ``,``, ``;``, tab o espacios:
           ``correo|clave|perfil|pin``.
        3. Bloques multilinea separados por línea en blanco (formato libre).
        """
        # Carga las cuentas ya existentes para este producto. Para stock por
        # perfiles guardamos email -> perfiles ya usados; el perfil vacío
        # representa una cuenta genérica/sin perfil.
        self._existing_profiles_by_email: dict[str, set[str]] = {}
        existing_qs = StockItem.objects.filter(product=product).only("credentials")
        for it in existing_qs:
            self._remember_text_duplicate_keys(it.credentials or "")
        self._duplicates_skipped = 0

        content = content.strip()
        if not content:
            return 0, 0
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
            created = self._import_csv(content, product, plan)
            return created, self._duplicates_skipped

        # Formato 3: bloques multilinea (cuando hay líneas vacías separadoras).
        # Solo aplicamos si hay al menos una línea vacía entre líneas no vacías;
        # si no, asumimos "una línea = una cuenta".
        has_blank_separators = any(
            not lines[i].strip() and i > 0 and i < len(lines) - 1
            for i in range(len(lines))
        )
        if has_blank_separators:
            created = self._import_blocks(content, product, plan)
            return created, self._duplicates_skipped

        # Formato 2: una línea por cuenta. Aceptamos cualquier separador común
        # (|, tab, ;, ,) o múltiples espacios entre email y clave.
        created = self._import_lines(non_empty, product, plan)
        return created, self._duplicates_skipped

    @staticmethod
    def _extract_emails(text: str) -> list[str]:
        import re
        return re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)

    @staticmethod
    def _normalize_profile(profile: str) -> str:
        return " ".join((profile or "").strip().lower().split())

    @classmethod
    def _extract_profile(cls, text: str) -> str:
        import re

        match = re.search(r"(?im)^(?:perfil|profile)\s*:\s*(.+)$", text)
        if not match:
            return ""
        return cls._normalize_profile(match.group(1))

    def _remember_duplicate_key(self, email: str, profile: str = "") -> None:
        email_key = (email or "").strip().lower()
        if not email_key:
            return
        profile_key = self._normalize_profile(profile)
        self._existing_profiles_by_email.setdefault(email_key, set()).add(profile_key)

    def _remember_text_duplicate_keys(self, text: str) -> None:
        profile = self._extract_profile(text)
        for email in self._extract_emails(text):
            self._remember_duplicate_key(email, profile)

    def _is_duplicate(self, email: str, profile: str = "") -> bool:
        """True si la cuenta/perfil ya existe en stock para este producto."""
        email_key = (email or "").strip().lower()
        if not email_key:
            return False

        existing_profiles = self._existing_profiles_by_email.get(email_key, set())
        incoming_profile = self._normalize_profile(profile)
        if not incoming_profile:
            is_duplicate = bool(existing_profiles)
        else:
            is_duplicate = incoming_profile in existing_profiles or "" in existing_profiles

        if is_duplicate:
            self._duplicates_skipped += 1
        return is_duplicate

    def _is_duplicate_text(self, text: str) -> bool:
        emails = self._extract_emails(text)
        if not emails:
            return False
        profile = self._extract_profile(text)
        return any(self._is_duplicate(email, profile) for email in emails)

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
            if self._is_duplicate(email, data.get("profile", "")):
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
            self._remember_duplicate_key(email, data.get("profile", ""))
            created += 1
        return created

    def _import_lines(self, lines: list[str], product: Product, plan: Plan | None) -> int:
        """Importa una cuenta por línea, autodetectando separadores comunes.

        Soporta como separadores entre email y clave: ``|``, tab, ``;``, ``,``,
        o múltiples espacios. Columnas: email, password, perfil (opcional),
        pin (opcional).
        """
        import re

        created = 0
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            # Autodetectar el separador. Probamos en orden de especificidad.
            for sep_pattern in (
                r"\s*\|\s*",       # pipe
                r"\t+",             # tab
                r"\s*;\s*",         # semicolon
                r"\s+:\s+",         # ' : '  (con espacios — más específico que ',' simple)
                r"\s*,\s*",         # comma
                r"\s{2,}",          # múltiples espacios
                r"\s+",             # espacios simples (último recurso)
            ):
                parts = [p.strip() for p in re.split(sep_pattern, line) if p.strip()]
                if len(parts) >= 2:
                    break
            else:
                # Línea con un solo token — la guardamos como bloque libre.
                if self._is_duplicate_text(line):
                    continue
                StockItem.objects.create(
                    product=product, plan=plan, credentials=line,
                )
                self._remember_text_duplicate_keys(line)
                created += 1
                continue
            email, password, *rest = parts
            if self._is_duplicate(email, rest[0] if rest else ""):
                continue
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
            self._remember_duplicate_key(email, rest[0] if rest else "")
            created += 1
        return created

    def _import_blocks(self, content: str, product: Product, plan: Plan | None) -> int:
        created = 0
        blocks = [b.strip() for b in content.split("\n\n") if b.strip()]
        for block in blocks:
            if self._is_duplicate_text(block):
                continue
            StockItem.objects.create(
                product=product, plan=plan, credentials=block,
            )
            self._remember_text_duplicate_keys(block)
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


@admin.register(ProductReview)
class ProductReviewAdmin(ModelAdmin):
    list_display = (
        "author_name", "product", "rating_display", "is_verified",
        "status", "has_photo", "created_at",
    )
    list_filter = ("status", "is_verified", "rating", "created_at")
    search_fields = ("author_name", "email", "comment", "title", "product__name")
    list_editable = ("status",)
    autocomplete_fields = ("product", "user", "order")
    readonly_fields = ("token", "token_used_at", "created_at", "updated_at")
    actions = ("approve_reviews", "reject_reviews")
    fieldsets = (
        ("Reseña", {
            "fields": (
                "product", "author_name", "city", "email",
                "rating", "title", "comment", "photo",
            ),
        }),
        ("Verificación y moderación", {
            "fields": (
                "order", "user", "is_verified",
                "status", "moderation_notes",
            ),
        }),
        ("Metadata", {
            "classes": ("collapse",),
            "fields": ("token", "token_used_at", "created_at", "updated_at"),
        }),
    )

    @display(description="Estrellas")
    def rating_display(self, obj):
        return "★" * obj.rating + "☆" * (5 - obj.rating)

    @display(description="Foto", boolean=True)
    def has_photo(self, obj):
        return bool(obj.photo)

    @admin.action(description="Aprobar reseñas seleccionadas")
    def approve_reviews(self, request, queryset):
        n = queryset.update(status=ProductReview.Status.APPROVED)
        self.message_user(request, f"{n} reseña(s) aprobadas.", level=messages.SUCCESS)

    @admin.action(description="Rechazar reseñas seleccionadas")
    def reject_reviews(self, request, queryset):
        n = queryset.update(status=ProductReview.Status.REJECTED)
        self.message_user(request, f"{n} reseña(s) rechazadas.", level=messages.WARNING)


@admin.register(PromoBanner)
class PromoBannerAdmin(ModelAdmin):
    list_display = (
        "name", "text_preview", "style", "is_active",
        "starts_at", "ends_at", "is_currently_active_display", "order",
    )
    list_filter = ("is_active", "style", "show_only_on_home")
    list_editable = ("is_active", "order")
    search_fields = ("name", "text", "coupon_code")
    fieldsets = (
        ("Contenido", {
            "fields": ("name", "text", "style"),
        }),
        ("Llamada a la acción", {
            "fields": ("cta_label", "cta_url", "coupon_code", "countdown_to"),
        }),
        ("Programación", {
            "fields": (
                "is_active", "starts_at", "ends_at",
                "show_only_on_home", "order",
            ),
        }),
    )

    @display(description="Texto")
    def text_preview(self, obj):
        return (obj.text[:60] + "…") if len(obj.text) > 60 else obj.text

    @display(description="En vivo", boolean=True)
    def is_currently_active_display(self, obj):
        return obj.is_currently_active


@admin.register(SiteSettings)
class SiteSettingsAdmin(ModelAdmin):
    """Singleton: una sola fila de configuración global del sitio."""

    fieldsets = (
        ("Marca", {
            "fields": ("site_name", "tagline", "logo", "favicon"),
        }),
        ("Hero / portada", {
            "fields": ("hero_title", "hero_subtitle", "hero_cta_text"),
        }),
        ("Contacto", {
            "fields": ("whatsapp_number", "whatsapp_message", "contact_email"),
        }),
        ("Redes sociales", {
            "fields": ("instagram_url", "tiktok_url", "facebook_url", "youtube_url"),
            "classes": ("collapse",),
        }),
        ("Canales de Telegram", {
            "fields": ("telegram_customer_channel_url", "telegram_distributor_channel_url"),
            "description": (
                "Enlaces públicos. El primero se muestra en la web a clientes finales "
                "(footer + página de contacto). El segundo se muestra solo dentro del "
                "panel de distribuidores."
            ),
        }),
        ("Información legal (Indecopi Perú)", {
            "fields": ("legal_business_name", "legal_ruc", "legal_address"),
            "classes": ("collapse",),
        }),
        ("SEO", {
            "fields": ("seo_default_image", "seo_meta_description"),
            "classes": ("collapse",),
        }),
        ("Tracking & Analytics", {
            "fields": ("ga4_measurement_id", "meta_pixel_id", "google_ads_id", "tiktok_pixel_id"),
            "description": (
                "IDs para activar Google Analytics 4, Meta Pixel y otros. "
                "Los pixels se cargan solo si el visitante acepta cookies."
            ),
            "classes": ("collapse",),
        }),
        ("Mantenimiento", {
            "fields": ("maintenance_mode", "maintenance_message"),
            "classes": ("collapse",),
        }),
    )
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Redirige siempre a la única instancia.
        obj = SiteSettings.load()
        from django.shortcuts import redirect
        from django.urls import reverse as _reverse
        return redirect(_reverse("admin:catalog_sitesettings_change", args=[obj.pk]))


@admin.register(Reclamacion)
class ReclamacionAdmin(ModelAdmin):
    """Libro de Reclamaciones digital (Indecopi).

    Las reclamaciones son inmutables (no editables salvo el estado y la
    respuesta). Mantenemos un registro auditable.
    """

    list_display = (
        "numero", "display_cliente", "tipo", "estado",
        "display_dias_restantes", "created_at",
    )
    list_filter = ("estado", "tipo", "tipo_bien", "created_at")
    search_fields = ("numero", "nombre", "email", "documento_numero", "telefono")
    date_hierarchy = "created_at"
    readonly_fields = (
        "numero", "nombre", "documento_tipo", "documento_numero",
        "domicilio", "telefono", "email",
        "es_menor", "padre_nombre", "padre_documento",
        "tipo_bien", "monto", "descripcion_bien", "pedido_referencia",
        "tipo", "detalle", "pedido_consumidor",
        "ip_address", "user_agent", "created_at",
    )
    fieldsets = (
        ("Identificación", {
            "fields": ("numero", "created_at", "estado"),
        }),
        ("Datos del consumidor", {
            "fields": (
                "nombre", ("documento_tipo", "documento_numero"),
                "domicilio", ("telefono", "email"),
                ("es_menor", "padre_nombre", "padre_documento"),
            ),
        }),
        ("Bien contratado", {
            "fields": (
                ("tipo_bien", "monto"),
                "descripcion_bien", "pedido_referencia",
            ),
        }),
        ("Reclamo", {
            "fields": ("tipo", "detalle", "pedido_consumidor"),
        }),
        ("Respuesta del proveedor", {
            "fields": ("respuesta", "respondido_en"),
        }),
        ("Auditoría", {
            "classes": ("collapse",),
            "fields": ("ip_address", "user_agent"),
        }),
    )

    def has_add_permission(self, request):
        return False  # Solo se crean por el formulario público

    def has_delete_permission(self, request, obj=None):
        return False  # Inmutables (Indecopi exige conservación)

    @display(description="Cliente")
    def display_cliente(self, obj: Reclamacion):
        return format_html(
            '<div class="jh-cell">'
            '<div class="jh-cell__name">{}</div>'
            '<div class="jh-cell__sub">{}</div>'
            '</div>',
            obj.nombre, obj.email or "\u2014",
        )

    @display(description="Vence en")
    def display_dias_restantes(self, obj: Reclamacion):
        d = obj.dias_restantes
        if obj.estado in ("respondido", "cerrado"):
            return chip("\u2014", tone="neutral")
        if d == 0:
            return chip("Vencido", tone="danger", icon="error")
        if d <= 3:
            return chip(f"{d}d", tone="warning", icon="schedule")
        return chip(f"{d}d", tone="success", icon="check_circle")


@admin.register(PlatformLanding)
class PlatformLandingAdmin(ModelAdmin):
    list_display = ("name", "slug", "is_published", "order", "accent_color_chip", "updated_at")
    list_editable = ("order", "is_published")
    list_filter = ("is_published",)
    search_fields = ("name", "slug", "seo_title")
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ("featured_products",)
    fieldsets = (
        ("Identificación", {
            "fields": ("name", "slug", "is_published", "order"),
        }),
        ("Hero / encabezado", {
            "fields": ("tagline", "hero_description", "logo", "accent_color"),
        }),
        ("SEO", {
            "fields": ("seo_title", "seo_description", "og_image"),
        }),
        ("Productos mostrados", {
            "fields": ("category", "featured_products"),
            "description": "Si seteas productos manualmente, tienen preferencia sobre la categoría.",
        }),
        ("Contenido adicional", {
            "fields": ("body_html", "faq"),
            "classes": ("collapse",),
            "description": (
                "FAQ: lista JSON [{\"q\": \"Pregunta\", \"a\": \"Respuesta\"}, ...]. "
                "body_html: HTML libre para la sección intermedia."
            ),
        }),
    )

    @display(description="Color")
    def accent_color_chip(self, obj):
        return format_html(
            '<span class="jh-color-dot" style="--c:{}"></span> '
            '<code class="jh-color-code">{}</code>',
            obj.accent_color or "#ec4899", obj.accent_color or "\u2014",
        )


@admin.register(BackInStockAlert)
class BackInStockAlertAdmin(ModelAdmin):
    list_display = (
        "email",
        "product",
        "plan",
        "status_chip",
        "created_at",
        "notified_at",
    )
    list_filter = ("status", "product")
    search_fields = ("email", "product__name", "plan__name")
    autocomplete_fields = ("product", "plan")
    readonly_fields = (
        "created_at", "notified_at", "user_agent", "ip",
    )
    actions = ["mark_cancelled", "mark_pending_again"]
    list_per_page = 50

    @display(description="Estado", label={
        "Pendiente": "warning",
        "Notificada": "success",
        "Cancelada": "secondary",
    })
    def status_chip(self, obj):
        return obj.get_status_display()

    def mark_cancelled(self, request, queryset):
        n = queryset.update(status=BackInStockAlert.Status.CANCELLED)
        self.message_user(
            request, f"{n} alerta(s) marcadas como canceladas.",
            messages.SUCCESS,
        )
    mark_cancelled.short_description = "Marcar como canceladas"

    def mark_pending_again(self, request, queryset):
        n = queryset.update(
            status=BackInStockAlert.Status.PENDING,
            notified_at=None,
        )
        self.message_user(
            request, f"{n} alerta(s) marcadas como pendientes de nuevo.",
            messages.SUCCESS,
        )
    mark_pending_again.short_description = "Marcar como pendientes (re-enviar)"
