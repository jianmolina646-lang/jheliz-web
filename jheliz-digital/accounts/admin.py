from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class DigitalUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Jheliz Digital", {"fields": ("role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Jheliz Digital", {"fields": ("role",)}),)
    list_display = (*UserAdmin.list_display, "role")
