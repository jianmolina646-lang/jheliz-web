from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, WalletTransaction


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "username", "email", "role", "distributor_approved",
        "wallet_balance", "is_staff", "date_joined",
    )
    list_filter = ("role", "distributor_approved", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name", "phone", "telegram_username")

    fieldsets = BaseUserAdmin.fieldsets + (
        ("Jheliz", {
            "fields": (
                "role", "phone", "telegram_username",
                "wallet_balance", "distributor_approved",
            )
        }),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Jheliz", {
            "fields": ("email", "role", "phone", "telegram_username"),
        }),
    )


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "amount", "balance_after", "reference", "created_at")
    list_filter = ("kind", "created_at")
    search_fields = ("user__username", "user__email", "reference")
    autocomplete_fields = ("user",)
    readonly_fields = ("balance_after", "created_at")
