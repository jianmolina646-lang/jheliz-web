"""Fixtures de sesión para pruebas de negocio; el flujo OTP tiene pruebas propias."""
from django_otp.plugins.otp_totp.models import TOTPDevice


def force_owner_login(client, owner):
    device, _ = TOTPDevice.objects.get_or_create(user=owner, name="business-test", confirmed=True)
    client.force_login(owner)
    session = client.session
    session["jheliz_control_otp_verified"] = True
    session["jheliz_control_otp_user"] = owner.pk
    session["jheliz_control_otp_device"] = device.persistent_id
    session.save()
