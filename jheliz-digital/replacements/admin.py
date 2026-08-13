from django.contrib import admin

from .models import Replacement


@admin.register(Replacement)
class ReplacementAdmin(admin.ModelAdmin):
    list_display = (
        "original_account",
        "replacement_account",
        "reason",
        "replaced_at",
        "created_by",
    )
    list_filter = ("reason", "replaced_at")
    readonly_fields = (
        "original_account",
        "replacement_account",
        "reason",
        "replaced_at",
        "notes",
        "created_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
