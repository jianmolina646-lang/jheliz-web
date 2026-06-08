"""Admin de Jheliz Control.

El módulo se usa sobre todo desde sus páginas custom (dashboard verde,
tablero de servicios, clientes). Igual registramos los modelos en el admin
de Unfold para edición/respaldo manual.
"""
from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import (
    Client,
    ControlSettings,
    Service,
    ServiceCategory,
    Subscription,
    Transaction,
)


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(ModelAdmin):
    list_display = ("name", "icon", "order")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("order", "name")


@admin.register(Service)
class ServiceAdmin(ModelAdmin):
    list_display = ("name", "category", "is_active", "created_at")
    list_filter = ("category", "is_active")
    search_fields = ("name",)


@admin.register(Client)
class ClientAdmin(ModelAdmin):
    list_display = ("name", "telegram", "whatsapp", "email", "created_at")
    search_fields = ("name", "telegram", "whatsapp", "email")


@admin.register(Subscription)
class SubscriptionAdmin(ModelAdmin):
    list_display = (
        "service", "client", "account_email", "plan", "profiles",
        "expires_at", "is_archived",
    )
    list_filter = ("service", "plan", "is_archived")
    search_fields = ("account_email", "client__name", "client__telegram")
    autocomplete_fields = ("client", "service")


@admin.register(Transaction)
class TransactionAdmin(ModelAdmin):
    list_display = ("kind", "amount", "currency", "description", "occurred_at")
    list_filter = ("kind", "currency")
    search_fields = ("description",)


@admin.register(ControlSettings)
class ControlSettingsAdmin(ModelAdmin):
    list_display = ("credits", "currency")
