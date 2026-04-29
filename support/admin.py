from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from .models import ReplyTemplate, Ticket, TicketMessage


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
