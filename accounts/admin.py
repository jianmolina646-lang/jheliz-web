from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.mail import send_mail
from django.template.loader import render_to_string

from .models import Role, User, WalletTransaction


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "username", "email", "role", "distributor_approved",
        "wallet_balance", "is_staff", "date_joined",
    )
    list_filter = ("role", "distributor_approved", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name", "phone", "telegram_username")
    actions = ["approve_distributor", "revoke_distributor"]

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

    @admin.action(description="Aprobar como distribuidor")
    def approve_distributor(self, request, queryset):
        count = 0
        for user in queryset:
            if user.role != Role.DISTRIBUIDOR:
                user.role = Role.DISTRIBUIDOR
            user.distributor_approved = True
            user.save(update_fields=["role", "distributor_approved"])
            if user.email:
                try:
                    html = render_to_string("emails/distributor_approved.html", {"user": user})
                    send_mail(
                        subject="Tu cuenta de distribuidor Jheliz ha sido aprobada",
                        message=(
                            f"Hola {user.get_full_name() or user.username},\n\n"
                            "Tu solicitud de distribuidor fue aprobada. Ya puedes ver los precios mayoristas "
                            "entrando a https://jhelizservicestv.xyz/distribuidor/panel/"
                        ),
                        from_email=None,
                        recipient_list=[user.email],
                        html_message=html,
                        fail_silently=True,
                    )
                except Exception:
                    pass
            count += 1
        self.message_user(request, f"{count} usuarios aprobados como distribuidor.")

    @admin.action(description="Revocar aprobación de distribuidor")
    def revoke_distributor(self, request, queryset):
        count = queryset.update(distributor_approved=False)
        self.message_user(request, f"{count} distribuidores desaprobados.")


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "amount", "balance_after", "reference", "created_at")
    list_filter = ("kind", "created_at")
    search_fields = ("user__username", "user__email", "reference")
    autocomplete_fields = ("user",)
    readonly_fields = ("balance_after", "created_at")
