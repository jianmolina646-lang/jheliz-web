from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from .models import CodeRequest, ReplyTemplate, Ticket, TicketMessage


@admin.register(ReplyTemplate)
class ReplyTemplateAdmin(ModelAdmin):
    list_display = ("name", "category", "is_active", "use_count", "last_used_at")
    list_filter = ("category", "is_active")
    search_fields = ("name", "subject", "body")
    list_filter_submit = True
    fieldsets = (
        (None, {
            "fields": ("name", "category", "is_active"),
        }),
        ("Contenido", {
            "fields": ("subject", "body"),
            "description": (
                "Variables disponibles: {nombre}, {pedido}, {producto}, "
                "{telefono}, {fecha}. Se reemplazan al insertar la plantilla en un ticket."
            ),
        }),
        ("Uso", {
            "fields": ("use_count", "last_used_at"),
            "classes": ("collapse",),
        }),
    )
    readonly_fields = ("use_count", "last_used_at")


class TicketMessageInline(TabularInline):
    model = TicketMessage
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Ticket)
class TicketAdmin(ModelAdmin):
    list_display = (
        "id", "user", "subject", "display_status", "order", "updated_at", "chat_link",
    )
    list_filter = ("status",)
    search_fields = ("subject", "user__username", "user__email")
    autocomplete_fields = ("user", "order")
    inlines = [TicketMessageInline]
    list_filter_submit = True
    actions = ("mark_resolved", "mark_pending_admin", "mark_closed")

    @admin.action(description="✓ Marcar como Resuelto")
    def mark_resolved(self, request, queryset):
        n = queryset.update(status=Ticket.Status.RESOLVED)
        self.message_user(request, f"{n} ticket(s) marcado(s) como Resueltos.")

    @admin.action(description="⏳ Marcar como Esperando soporte")
    def mark_pending_admin(self, request, queryset):
        n = queryset.update(status=Ticket.Status.PENDING_ADMIN)
        self.message_user(request, f"{n} ticket(s) marcado(s) como Pendientes de respuesta.")

    @admin.action(description="🗄 Cerrar ticket")
    def mark_closed(self, request, queryset):
        n = queryset.update(status=Ticket.Status.CLOSED)
        self.message_user(request, f"{n} ticket(s) cerrado(s).")

    @display(
        description="Estado",
        ordering="status",
        label={
            Ticket.Status.OPEN: "info",
            Ticket.Status.PENDING_USER: "warning",
            Ticket.Status.PENDING_ADMIN: "warning",
            Ticket.Status.RESOLVED: "success",
            Ticket.Status.CLOSED: "",
        },
    )
    def display_status(self, obj: Ticket):
        return obj.status, obj.get_status_display()

    @admin.display(description="Chat")
    def chat_link(self, obj: Ticket) -> str:
        url = reverse("admin_support_chat", args=[obj.pk])
        return format_html(
            '<a href="{}" class="inline-flex items-center gap-1 px-3 py-1 rounded-md '
            'bg-primary-500 hover:bg-primary-400 text-white text-xs font-semibold">'
            '💬 Responder</a>',
            url,
        )


@admin.register(CodeRequest)
class CodeRequestAdmin(ModelAdmin):
    list_display = (
        "id", "display_status", "platform", "requested_code_type",
        "account_email", "audience", "order_number", "created_at",
        "responded_at",
    )
    list_filter = ("status", "audience", "platform", "requested_code_type", "code_type")
    search_fields = (
        "account_email", "contact_email", "order_number", "code", "note",
    )
    date_hierarchy = "created_at"
    autocomplete_fields = ("user", "order")
    list_filter_submit = True
    fieldsets = (
        ("Solicitud", {
            "fields": (
                "audience", "platform", "requested_code_type",
                "account_email", "contact_email", "order_number",
                "order", "user", "note",
            ),
        }),
        ("Respuesta", {
            "description": (
                "Pega el código que recibiste en tu buzón. Solo se permiten "
                "códigos de login / activación / hogar / link de restablecer "
                "contraseña. Nunca publiques códigos de cambio de correo o "
                "cambio de contraseña."
            ),
            "fields": ("status", "code", "code_type", "admin_note", "reject_reason"),
        }),
        ("Trazabilidad", {
            "classes": ("collapse",),
            "fields": (
                "token", "ip_address", "user_agent",
                "created_at", "responded_at", "responded_by",
            ),
        }),
    )
    readonly_fields = (
        "token", "ip_address", "user_agent",
        "created_at", "responded_at", "responded_by",
    )

    @display(
        description="Estado",
        ordering="status",
        label={
            CodeRequest.Status.PENDING: "warning",
            CodeRequest.Status.DELIVERED: "success",
            CodeRequest.Status.REJECTED: "danger",
            CodeRequest.Status.EXPIRED: "",
        },
    )
    def display_status(self, obj: CodeRequest):
        return obj.status, obj.get_status_display()

    def save_model(self, request, obj: CodeRequest, form, change):
        # Si el admin introduce un código y no cambió el status manualmente,
        # marcamos automáticamente como entregado y registramos quién respondió.
        prev = CodeRequest.objects.filter(pk=obj.pk).first() if obj.pk else None
        code_new = (obj.code or "").strip()
        code_prev = (prev.code if prev else "") or ""
        if code_new and code_new != code_prev and obj.status == CodeRequest.Status.PENDING:
            obj.status = CodeRequest.Status.DELIVERED
        # Si el admin no eligió el tipo de código entregado pero el cliente sí
        # había seleccionado uno al pedir, lo copiamos.
        if not obj.code_type and obj.requested_code_type:
            obj.code_type = obj.requested_code_type
        if obj.status == CodeRequest.Status.DELIVERED and obj.responded_at is None:
            from django.utils import timezone as _tz
            obj.responded_at = _tz.now()
            obj.responded_by = request.user
        super().save_model(request, obj, form, change)
