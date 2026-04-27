from django.contrib import admin

from .models import Ticket, TicketMessage


class TicketMessageInline(admin.TabularInline):
    model = TicketMessage
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "subject", "status", "order", "updated_at")
    list_filter = ("status",)
    search_fields = ("subject", "user__username", "user__email")
    autocomplete_fields = ("user", "order")
    inlines = [TicketMessageInline]
