"""Admin classic para auditoría/listado de salas y mensajes.

La UX principal del operador es ``/panel-jheliz-2026/livechat/`` (vista
custom). El admin clásico queda como vista de auditoría / inspección.
"""

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import ChatMessage, ChatRoom


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    fields = ("created_at", "sender", "sender_user", "body")
    readonly_fields = ("created_at", "sender", "sender_user")
    extra = 0
    can_delete = False
    show_change_link = False
    ordering = ("created_at",)

    def has_add_permission(self, request, obj=None):
        # No queremos que el staff cree mensajes desde el admin clásico —
        # eso vive en /panel-jheliz-2026/livechat/.
        return False


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = (
        "id", "display_name_col", "customer_email", "status",
        "messages_count", "last_message_at", "created_at", "open_link",
    )
    list_filter = ("status",)
    search_fields = ("customer_email", "customer_name", "user__username")
    readonly_fields = (
        "token", "user", "page_url", "user_agent", "ip",
        "created_at", "last_message_at",
        "last_admin_seen_at", "last_customer_seen_at",
    )
    inlines = [ChatMessageInline]
    ordering = ("-last_message_at", "-created_at")

    @admin.display(description="Cliente")
    def display_name_col(self, obj: ChatRoom) -> str:
        return obj.display_name

    @admin.display(description="# Mensajes")
    def messages_count(self, obj: ChatRoom) -> int:
        return obj.messages.count()

    @admin.display(description="Abrir")
    def open_link(self, obj: ChatRoom):
        url = reverse("admin_livechat_detail", args=[obj.pk])
        return format_html(
            '<a href="{}" class="button" style="white-space:nowrap;">💬 Abrir</a>',
            url,
        )


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "room", "sender", "sender_user", "short_body", "created_at")
    list_filter = ("sender",)
    search_fields = ("body", "room__customer_email")
    readonly_fields = ("room", "sender", "sender_user", "body", "created_at")
    ordering = ("-created_at",)

    @admin.display(description="Mensaje")
    def short_body(self, obj: ChatMessage) -> str:
        return (obj.body or "")[:80]
