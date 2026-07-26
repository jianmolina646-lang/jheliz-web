"""Operaciones centrales de Jheliz Control compartidas por web y Telegram."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from config.date_utils import add_service_duration

from .forms import ClientForm
from .models import (
    Client,
    ControlSettings,
    Service,
    Subscription,
    TelegramActionReceipt,
    Transaction,
)


def clients_for_owner(owner_id):
    return Client.objects.filter(owner_id=owner_id)


def subscriptions_for_owner(owner_id):
    return Subscription.objects.filter(
        owner_id=owner_id,
        client__owner_id=owner_id,
        service__owner_id=owner_id,
        is_archived=False,
    )


def client_for_owner(owner_id, client_id):
    return clients_for_owner(owner_id).filter(pk=client_id).first()


def subscription_for_owner(owner_id, subscription_id):
    return subscriptions_for_owner(owner_id).filter(pk=subscription_id).first()


def search_clients(owner_id, query):
    query = (query or "").strip()
    qs = clients_for_owner(owner_id)
    if query:
        qs = qs.filter(
            Q(name__icontains=query)
            | Q(whatsapp__icontains=query)
            | Q(email__icontains=query)
            | Q(telegram__icontains=query)
            | Q(subscriptions__account_email__icontains=query)
        ).distinct()
    return qs.order_by("name")


def validate_client_data(data, instance=None):
    form = ClientForm(data, instance=instance)
    return form, form.is_valid()


def _decimal(value):
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


@transaction.atomic
def create_client(owner, data, idempotency_key=None):
    if idempotency_key and not _claim(owner.id, idempotency_key, "client_create"):
        return None, "duplicate"
    form, valid = validate_client_data(data)
    if not valid:
        return None, form.errors.get_json_data()
    client = form.save(commit=False)
    client.owner = owner
    client.save()
    return client, None


@transaction.atomic
def update_client(owner, client_id, data, idempotency_key=None):
    client = clients_for_owner(owner.id).select_for_update().filter(pk=client_id).first()
    if not client:
        return None, "not_found"
    if idempotency_key and not _claim(owner.id, idempotency_key, "client_update"):
        return None, "duplicate"
    form, valid = validate_client_data(data, instance=client)
    if not valid:
        return None, form.errors.get_json_data()
    return form.save(), None


@transaction.atomic
def create_subscription(owner, data, idempotency_key=None):
    client = clients_for_owner(owner.id).filter(pk=data.get("client_id")).first()
    service = Service.objects.filter(owner=owner, pk=data.get("service_id")).first()
    if not client or not service:
        return None, "not_found"
    if idempotency_key and not _claim(owner.id, idempotency_key, "subscription_create"):
        return None, "duplicate"
    account_email = (data.get("account_email") or "").strip()
    if not account_email:
        return None, "account_required"
    plan = (
        Subscription.Plan.COMPLETA
        if data.get("plan") == Subscription.Plan.COMPLETA
        else Subscription.Plan.PERFIL
    )
    try:
        profiles = max(1, min(7, int(data.get("profiles") or 1)))
    except (TypeError, ValueError):
        profiles = 1
    if plan == Subscription.Plan.COMPLETA:
        profiles = 1
    try:
        days = max(1, min(3660, int(data.get("duration_days") or 30)))
    except (TypeError, ValueError):
        days = 30
    starts_at = data.get("starts_at") or timezone.now()
    expires_at = data.get("expires_at") or add_service_duration(starts_at, days)
    control = ControlSettings.load(owner)
    cost = _decimal(data.get("cost"))
    investment = _decimal(data.get("investment"))
    sub = Subscription.objects.create(
        owner=owner,
        client=client,
        service=service,
        account_email=account_email,
        account_password=(data.get("account_password") or "").strip(),
        plan=plan,
        profiles=profiles,
        profile_name=(data.get("profile_name") or "").strip(),
        profile_pin=(data.get("profile_pin") or "").strip(),
        plan_label=(data.get("plan_label") or "").strip(),
        currency=control.currency or "S/",
        cost=cost,
        investment=investment,
        starts_at=starts_at,
        expires_at=expires_at,
    )
    if cost > 0:
        Transaction.objects.create(
            owner=owner,
            kind=Transaction.Kind.INCOME,
            amount=cost,
            currency=sub.currency,
            description=f"Venta {service.name} · {client.name}",
            client=client,
            subscription=sub,
        )
    if investment > 0:
        Transaction.objects.create(
            owner=owner,
            kind=Transaction.Kind.EXPENSE,
            amount=investment,
            currency=sub.currency,
            description=f"Inversión {service.name}",
            client=client,
            subscription=sub,
        )
    return sub, None


@transaction.atomic
def renew_subscription(owner, subscription_id, days, idempotency_key=None):
    sub = (
        subscriptions_for_owner(owner.id)
        .select_for_update()
        .filter(pk=subscription_id)
        .first()
    )
    if not sub:
        return None, "not_found"
    if idempotency_key and not _claim(owner.id, idempotency_key, "subscription_renew"):
        return None, "duplicate"
    try:
        duration = int(days)
    except (TypeError, ValueError):
        return None, "invalid_days"
    if duration < 1 or duration > 3660:
        return None, "invalid_days"
    # Mantener el día de vencimiento original también para suscripciones
    # vencidas. Así el resumen previo y la fecha finalmente guardada coinciden.
    base = sub.expires_at or timezone.now()
    sub.expires_at = add_service_duration(base, duration)
    sub.save(update_fields=["expires_at", "updated_at"])
    return sub, None


@transaction.atomic
def delete_client(owner, client_id, idempotency_key=None):
    client = clients_for_owner(owner.id).select_for_update().filter(pk=client_id).first()
    if not client:
        return False, "not_found"
    if idempotency_key and not _claim(owner.id, idempotency_key, "client_delete"):
        return False, "duplicate"
    client.delete()
    return True, None


def owner_summary(owner_id):
    now = timezone.now()
    soon = now + timedelta(days=3)
    clients = clients_for_owner(owner_id).count()
    subscriptions = subscriptions_for_owner(owner_id)
    return {
        "clients": clients,
        "active": subscriptions.filter(expires_at__gt=soon).count(),
        "due": subscriptions.filter(expires_at__gt=now, expires_at__lte=soon).count(),
        "expired": subscriptions.filter(expires_at__lte=now).count(),
        "subscriptions": subscriptions.count(),
    }


def owner_finances(owner):
    settings_obj = ControlSettings.load(owner)
    income = (
        Transaction.objects.filter(owner=owner, kind=Transaction.Kind.INCOME)
        .aggregate(value=Sum("amount"))["value"]
        or 0
    )
    expense = (
        Transaction.objects.filter(owner=owner, kind=Transaction.Kind.EXPENSE)
        .aggregate(value=Sum("amount"))["value"]
        or 0
    )
    return {
        "credits": settings_obj.credits,
        "currency": settings_obj.currency,
        "income": income,
        "expense": expense,
        "net": income - expense,
    }


def _claim(owner_id, key, action):
    try:
        # El savepoint interno permite capturar una clave repetida sin dejar
        # rota la transacción exterior de la operación de negocio.
        with transaction.atomic():
            TelegramActionReceipt.objects.create(
                owner_id=owner_id,
                key=key,
                action=action,
            )
    except IntegrityError:
        return False
    return True
