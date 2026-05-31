from django.contrib import admin, messages
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action as unfold_action

from .models import AssignedEmail, CodeBotClient


class AssignedEmailInline(TabularInline):
    model = AssignedEmail
    extra = 1
    fields = ("email", "note", "created_at")
    readonly_fields = ("created_at",)


@admin.register(CodeBotClient)
class CodeBotClientAdmin(ModelAdmin):
    list_display = (
        "display_name",
        "telegram_username",
        "telegram_chat_id",
        "is_active",
        "email_count",
        "last_seen_at",
        "created_at",
    )
    list_filter = ("is_active", "created_at")
    search_fields = (
        "display_name",
        "telegram_username",
        "telegram_chat_id",
        "emails__email",
    )
    readonly_fields = ("telegram_chat_id", "created_at", "last_seen_at")
    inlines = (AssignedEmailInline,)
    actions = ("activar_clientes", "desactivar_clientes")
    list_per_page = 50

    @admin.display(description="Correos")
    def email_count(self, obj: CodeBotClient) -> int:
        return obj.emails.count()

    @unfold_action(description="Activar seleccionados")
    def activar_clientes(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} cliente(s) activado(s).", messages.SUCCESS)

    @unfold_action(description="Desactivar seleccionados")
    def desactivar_clientes(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} cliente(s) desactivado(s).", messages.WARNING)


@admin.register(AssignedEmail)
class AssignedEmailAdmin(ModelAdmin):
    list_display = ("email", "client", "note", "created_at")
    search_fields = ("email", "client__display_name", "client__telegram_username")
    list_filter = ("created_at",)
    autocomplete_fields = ("client",)
