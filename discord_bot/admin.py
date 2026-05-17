from django.contrib import admin

from .models import DiscordOrderThread


@admin.register(DiscordOrderThread)
class DiscordOrderThreadAdmin(admin.ModelAdmin):
    list_display = (
        "order", "thread_id", "channel_id", "last_status_posted", "created_at",
    )
    search_fields = ("order__email", "thread_id", "channel_id")
    readonly_fields = (
        "order", "channel_id", "thread_id", "root_message_id", "created_at",
    )
    list_filter = ("last_status_posted", "created_at")
