"""Signals de autenticación y cambios sensibles."""

from __future__ import annotations

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import User
from .security_events import record_security_event

try:
    from axes.signals import user_locked_out
except ImportError:  # pragma: no cover
    user_locked_out = None


@receiver(user_login_failed)
def login_failed(sender, credentials, request, **kwargs):
    record_security_event("auth.login_failed", request=request, username=str(credentials.get("username") or credentials.get("email") or ""))


@receiver(user_logged_in)
def login_succeeded(sender, request, user, **kwargs):
    record_security_event("auth.staff_login_succeeded" if user.is_staff else "auth.login_succeeded", request=request, actor=user, severity="warning" if user.is_staff else "info")


@receiver(user_logged_out)
def logout_recorded(sender, request, user, **kwargs):
    record_security_event("auth.logout", request=request, actor=user, severity="info")


if user_locked_out is not None:
    @receiver(user_locked_out)
    def login_locked(sender, request, username, ip_address, **kwargs):
        record_security_event(
            "auth.login_locked", request=request, username=str(username or ""),
            severity="critical", metadata={"axes_ip": str(ip_address or "")}, alert=True,
        )


@receiver(pre_save, sender=User)
def capture_sensitive_user_changes(sender, instance, **kwargs):
    if not instance.pk:
        instance._security_previous = None
        return
    instance._security_previous = User.objects.filter(pk=instance.pk).values(
        "password", "email", "is_staff", "is_superuser", "is_active", "role", "distributor_approved"
    ).first()


@receiver(post_save, sender=User)
def record_sensitive_user_changes(sender, instance, created, **kwargs):
    previous = getattr(instance, "_security_previous", None)
    if created:
        if instance.is_staff or instance.is_superuser:
            record_security_event("account.privileged_created", username=instance.get_username(), severity="critical", alert=True, metadata={"subject_user_id": instance.pk})
        return
    if not previous:
        return
    changes = {}
    for field in ("email", "is_staff", "is_superuser", "is_active", "role", "distributor_approved"):
        new = getattr(instance, field)
        if previous[field] != new:
            changes[field] = [previous[field], new]
    if changes:
        critical = any(field in changes for field in ("is_staff", "is_superuser", "is_active", "role"))
        record_security_event("account.privileges_changed", username=instance.get_username(), severity="critical" if critical else "warning", metadata={"subject_user_id": instance.pk, "changes": changes}, alert=critical)
    if previous["password"] != instance.password:
        record_security_event("account.password_changed", username=instance.get_username(), severity="critical", alert=True, metadata={"subject_user_id": instance.pk})


def connect_otp_signals():
    from django_otp.plugins.otp_static.models import StaticDevice
    from django_otp.plugins.otp_totp.models import TOTPDevice

    def otp_saved(sender, instance, created, **kwargs):
        record_security_event(
            "account.2fa_device_created" if created else "account.2fa_device_changed",
            username=instance.user.get_username(), severity="critical", alert=True,
            metadata={"subject_user_id": instance.user_id, "device_type": sender.__name__, "confirmed": bool(getattr(instance, "confirmed", False))},
        )

    def otp_deleted(sender, instance, **kwargs):
        record_security_event("account.2fa_device_deleted", username=instance.user.get_username(), severity="critical", alert=True, metadata={"subject_user_id": instance.user_id, "device_type": sender.__name__})

    for model in (TOTPDevice, StaticDevice):
        post_save.connect(otp_saved, sender=model, weak=False, dispatch_uid=f"security_{model.__name__}_saved")
        post_delete.connect(otp_deleted, sender=model, weak=False, dispatch_uid=f"security_{model.__name__}_deleted")
