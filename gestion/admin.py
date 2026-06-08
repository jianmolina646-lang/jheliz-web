"""Admin de Jheliz Control.

El módulo se usa sobre todo desde sus páginas custom (dashboard verde,
tablero de servicios, clientes). Igual registramos los modelos en el admin
de Unfold para edición/respaldo manual.
"""
from django.contrib import admin, messages
from unfold.admin import ModelAdmin

from .models import (
    Client,
    ControlSettings,
    SaasSettings,
    Service,
    ServiceCategory,
    Subscription,
    Tenant,
    TenantPayment,
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
    list_display = ("owner", "credits", "currency")


@admin.register(Tenant)
class TenantAdmin(ModelAdmin):
    list_display = (
        "business_name", "user", "plan_expires_at", "subscription_active",
        "is_blocked", "created_at",
    )
    list_filter = ("is_blocked",)
    search_fields = ("business_name", "user__username", "user__email", "whatsapp")
    autocomplete_fields = ("user",)
    actions = ("extend_30",)

    @admin.display(boolean=True, description="Alquiler vigente")
    def subscription_active(self, obj):
        return obj.subscription_active

    @admin.action(description="Sumar 30 días de alquiler")
    def extend_30(self, request, queryset):
        for tenant in queryset:
            tenant.extend(30)
        self.message_user(request, f"{queryset.count()} inquilino(s) +30 días.", messages.SUCCESS)


@admin.register(TenantPayment)
class TenantPaymentAdmin(ModelAdmin):
    list_display = (
        "tenant", "amount", "days", "status", "created_at", "reviewed_at",
    )
    list_filter = ("status",)
    search_fields = ("tenant__business_name", "tenant__user__username")
    autocomplete_fields = ("tenant",)
    actions = ("approve_payments", "reject_payments")

    @admin.action(description="Aprobar pago (activa/renueva 30 días)")
    def approve_payments(self, request, queryset):
        n = 0
        for pay in queryset.filter(status=TenantPayment.Status.PENDING):
            pay.approve()
            n += 1
        self.message_user(request, f"{n} pago(s) aprobado(s).", messages.SUCCESS)

    @admin.action(description="Rechazar pago")
    def reject_payments(self, request, queryset):
        n = queryset.filter(status=TenantPayment.Status.PENDING).count()
        for pay in queryset.filter(status=TenantPayment.Status.PENDING):
            pay.reject("Rechazado desde el admin.")
        self.message_user(request, f"{n} pago(s) rechazado(s).", messages.WARNING)


@admin.register(SaasSettings)
class SaasSettingsAdmin(ModelAdmin):
    list_display = ("monthly_price", "yape_holder", "yape_phone")
