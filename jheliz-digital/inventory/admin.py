from django.contrib import admin

from .models import DigitalAccount


@admin.register(DigitalAccount)
class DigitalAccountAdmin(admin.ModelAdmin):
    list_display = ("service", "masked_email", "status", "renewal_date", "billing_method")
    list_filter = ("service", "status", "billing_method")
    search_fields = ("email", "country")
    readonly_fields = ("encrypted_password", "created_at", "updated_at")

    def get_exclude(self, request, obj=None):
        return ("encrypted_password",)
