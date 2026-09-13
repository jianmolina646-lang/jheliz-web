"""Server-side verification for manual Yape notifications."""

import secrets
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Tenant, TenantPayment


def _normalized_name(value):
    return " ".join((value or "").casefold().split())


@transaction.atomic
def verify_and_approve_yape(*, payment_id, actor, security_code, amount, payer_name):
    payment = TenantPayment.objects.select_for_update().get(pk=payment_id)
    if payment.status != TenantPayment.Status.PENDING:
        raise ValidationError("Este pago ya fue procesado.")
    if payment.method != TenantPayment.Method.YAPE:
        raise ValidationError("Este pago no corresponde a Yape.")
    try:
        received_amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("El monto recibido no es válido.")
    valid = (
        secrets.compare_digest((security_code or "").strip(), payment.yape_security_code)
        and received_amount == payment.amount
        and secrets.compare_digest(
            _normalized_name(payer_name).encode("utf-8"),
            _normalized_name(payment.payer_name).encode("utf-8"),
        )
    )
    if not valid:
        raise ValidationError("Los datos no coinciden con el pago declarado.")

    tenant = Tenant.objects.select_for_update().get(pk=payment.tenant_id)
    payment.status = TenantPayment.Status.APPROVED
    payment.reviewed_at = timezone.now()
    payment.verified_at = payment.reviewed_at
    payment.verified_by = actor
    payment.save(update_fields=["status", "reviewed_at", "verified_at", "verified_by"])
    tenant.extend(payment.days or 30)
    return payment
