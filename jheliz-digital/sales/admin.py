from django.contrib import admin

from .models import Sale


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("account", "amount", "payment_method", "sold_at", "created_by")
    list_filter = ("payment_method", "sold_at")
    search_fields = ("account__email", "account__service__name", "payment_reference")
    readonly_fields = (
        "account",
        "amount",
        "payment_method",
        "payment_reference",
        "sold_at",
        "notes",
        "created_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
