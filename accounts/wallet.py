"""Servicio del wallet de distribuidores.

Centraliza las operaciones que mueven saldo (acreditar, debitar,
aprobar/rechazar recargas) en transacciones atómicas para evitar
condiciones de carrera y mantener consistencia entre
``User.wallet_balance`` y la tabla de movimientos.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import WalletRecharge, WalletTransaction

User = get_user_model()


class InsufficientFundsError(Exception):
    """El usuario no tiene saldo suficiente para una operaci\u00f3n de d\u00e9bito."""


@dataclass
class WalletResult:
    ok: bool
    message: str
    transaction: Optional[WalletTransaction] = None


def _credit(user, amount: Decimal, kind: str, reference: str = "") -> WalletTransaction:
    """Suma saldo (operaci\u00f3n at\u00f3mica con select_for_update)."""
    if amount <= Decimal("0"):
        raise ValueError("El monto debe ser positivo.")
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        new_balance = (locked.wallet_balance or Decimal("0")) + amount
        locked.wallet_balance = new_balance
        locked.save(update_fields=["wallet_balance"])
        tx = WalletTransaction.objects.create(
            user=locked, kind=kind, amount=amount,
            balance_after=new_balance, reference=reference,
        )
    return tx


def _debit(user, amount: Decimal, kind: str, reference: str = "") -> WalletTransaction:
    """Resta saldo. Falla si no alcanza."""
    if amount <= Decimal("0"):
        raise ValueError("El monto debe ser positivo.")
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        current = locked.wallet_balance or Decimal("0")
        if current < amount:
            raise InsufficientFundsError(
                f"Saldo insuficiente: tiene S/ {current:,.2f}, necesita S/ {amount:,.2f}."
            )
        new_balance = current - amount
        locked.wallet_balance = new_balance
        locked.save(update_fields=["wallet_balance"])
        tx = WalletTransaction.objects.create(
            user=locked, kind=kind, amount=amount,
            balance_after=new_balance, reference=reference,
        )
    return tx


def deposit(user, amount: Decimal, reference: str = "") -> WalletTransaction:
    """Acreditar saldo (recarga aprobada o ajuste positivo)."""
    return _credit(user, amount, WalletTransaction.Kind.RECARGA, reference=reference)


def manual_adjust(user, amount: Decimal, reference: str = "") -> WalletTransaction:
    """Ajuste manual del admin (puede ser + o -; aqu\u00ed positivo)."""
    return _credit(user, amount, WalletTransaction.Kind.AJUSTE, reference=reference)


def charge_for_order(user, amount: Decimal, order) -> WalletTransaction:
    """Debitar saldo para pagar un pedido."""
    ref = f"Pedido #{order.display_number}" if hasattr(order, "display_number") else f"Pedido #{order.pk}"
    return _debit(user, amount, WalletTransaction.Kind.COMPRA, reference=ref)


def refund_order(user, amount: Decimal, order) -> WalletTransaction:
    """Reembolsar al wallet (orden cancelada o devuelta)."""
    ref = f"Reembolso pedido #{order.display_number}" if hasattr(order, "display_number") else f"Reembolso pedido #{order.pk}"
    return _credit(user, amount, WalletTransaction.Kind.REEMBOLSO, reference=ref)


def approve_recharge(recharge: WalletRecharge, by_user=None) -> WalletResult:
    """Aprobar solicitud de recarga: acredita saldo + crea movimiento."""
    if recharge.status != WalletRecharge.Status.PENDING:
        return WalletResult(
            False, f"Esta solicitud ya est\u00e1 {recharge.get_status_display().lower()}."
        )
    if recharge.amount <= Decimal("0"):
        return WalletResult(False, "El monto debe ser mayor a 0.")
    with transaction.atomic():
        tx = deposit(
            recharge.user, recharge.amount,
            reference=f"Recarga #{recharge.pk} ({recharge.get_method_display()})",
        )
        recharge.status = WalletRecharge.Status.APPROVED
        recharge.decided_at = timezone.now()
        recharge.decided_by = by_user
        recharge.transaction = tx
        recharge.rejection_reason = ""
        recharge.save(update_fields=[
            "status", "decided_at", "decided_by", "transaction", "rejection_reason",
        ])
    return WalletResult(
        True,
        f"Recarga aprobada. Se acreditaron S/ {recharge.amount:,.2f} a {recharge.user}.",
        transaction=tx,
    )


def reject_recharge(recharge: WalletRecharge, reason: str, by_user=None) -> WalletResult:
    if recharge.status != WalletRecharge.Status.PENDING:
        return WalletResult(
            False, f"Esta solicitud ya est\u00e1 {recharge.get_status_display().lower()}."
        )
    recharge.status = WalletRecharge.Status.REJECTED
    recharge.decided_at = timezone.now()
    recharge.decided_by = by_user
    recharge.rejection_reason = (reason or "").strip() or "Sin motivo especificado."
    recharge.save(update_fields=[
        "status", "decided_at", "decided_by", "rejection_reason",
    ])
    return WalletResult(True, "Solicitud rechazada.")
