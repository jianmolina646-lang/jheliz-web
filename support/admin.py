from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from .models import Ticket, TicketMessage


class TicketMessageInline(TabularInline):
    model = TicketMessage
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Ticket)
class TicketAdmin(ModelAdmin):
    list_display = ("id", "user", "subject", "display_status", "order", "updated_at")
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
