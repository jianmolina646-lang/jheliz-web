from django.contrib import admin

from .models import DigitalService


@admin.register(DigitalService)
class DigitalServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    readonly_fields = ("slug", "created_at", "updated_at")
