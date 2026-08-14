"""Panel del **dueño/proveedor** de jheliztv.xyz, montado en ``/control/``.

Separado de la web del inquilino (``tenant_views``) y del admin de la tienda
(``/panel-jheliz-2026/``). Solo accede el **staff** (el dueño): desde acá ve los
inquilinos registrados en jheliztv.xyz, controla su alquiler (suscripción) y
aprueba/rechaza los pagos Yape — sin tocar la tienda.

Vive bajo ``config.urls_jheliztv`` (solo se sirve en el dominio jheliztv.xyz),
así que el futuro dueño de la tienda no lo ve desde su propio dominio.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from functools import wraps
import secrets

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.http import FileResponse
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.http import require_POST

from .models import (
    Client,
    SaasSettings,
    Service,
    Subscription,
    TelegramConnection,
    Tenant,
    TenantPayment,
    Transaction,
)

User = get_user_model()


def owner_required(view):
    """Exige el permiso global explícito del dueño de la plataforma."""

    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if not (
            request.user.is_authenticated
            and request.user.has_perm("gestion.manage_tenants")
        ):
            return redirect("jheliztv_control_login")
        return view(request, *args, **kwargs)

    return _wrapped


def control_login(request):
    if request.user.is_authenticated and request.user.has_perm("gestion.manage_tenants"):
        return redirect("jheliztv_control_dashboard")
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        user = authenticate(request, username=username, password=password)
        if user is None or not user.has_perm("gestion.manage_tenants"):
            messages.error(request, "Acceso solo para el administrador.")
            return render(request, "jheliztv/control/login.html", {"username": username})
        login(request, user)
        return redirect("jheliztv_control_dashboard")
    return render(request, "jheliztv/control/login.html", {})


def control_logout(request):
    logout(request)
    return redirect("jheliztv_control_login")


@owner_required
def control_dashboard(request):
    tenants = _control_tenant_rows(Tenant.objects.select_related("user"))
    pending = list(
        TenantPayment.objects.filter(status=TenantPayment.Status.PENDING)
        .select_related("tenant", "tenant__user").order_by("-created_at")[:5]
    )
    kpi = _control_kpi(tenants)
    recent = sorted(
        tenants, key=lambda tenant: tenant.last_activity_at or tenant.created_at, reverse=True,
    )[:8]
    return render(request, "jheliztv/control/dashboard.html", {
        "title": "Resumen", "jc_control_active": "dashboard",
        "kpi": kpi, "recent": recent, "pending": pending,
    })


def _control_tenant_rows(queryset):
    tenants = list(queryset.order_by("-created_at"))
    online_since = timezone.now() - timedelta(minutes=5)
    section_labels = {
        "/app/": "Inicio", "/app/clientes/": "Clientes",
        "/app/servicios/": "Servicios", "/app/correos/": "Correos",
        "/app/soporte/": "Soporte", "/app/renovaciones/": "Renovaciones",
        "/app/telegram/": "Telegram", "/app/whatsapp/": "WhatsApp",
        "/app/configuracion/monedas/": "Monedas", "/suscripcion/": "Suscripción",
    }
    telegram_by_owner = {
        connection.owner_id: connection
        for connection in TelegramConnection.objects.select_related("owner")
    }

    for t in tenants:
        t.telegram_connection = telegram_by_owner.get(t.user_id)
        t.is_online = bool(t.last_activity_at and t.last_activity_at >= online_since)
        matching_sections = [
            (prefix, label) for prefix, label in section_labels.items()
            if t.last_activity_path.startswith(prefix)
        ]
        t.activity_section = (
            max(matching_sections, key=lambda item: len(item[0]))[1]
            if matching_sections else ("Sin actividad" if not t.last_activity_path else "Otra sección")
        )
        if t.is_blocked:
            t.estado, t.estado_color = "Bloqueado", "red"
        elif t.subscription_active:
            t.estado, t.estado_color = "Activo", "green"
        else:
            t.estado, t.estado_color = "Vencido", "red"

    return tenants


def _control_kpi(tenants):
    total = len(tenants)
    return {
        "total": total,
        "activos": sum(1 for tenant in tenants if tenant.subscription_active),
        "vencidos": sum(1 for tenant in tenants if not tenant.subscription_active),
        "online": sum(1 for tenant in tenants if tenant.is_online),
        "demos": sum(1 for tenant in tenants if tenant.is_demo and tenant.subscription_active),
        "pendientes": TenantPayment.objects.filter(status=TenantPayment.Status.PENDING).count(),
        "subs": Subscription.objects.filter(is_archived=False).count(),
        "telegram": sum(
            1 for tenant in tenants
            if tenant.telegram_connection and tenant.telegram_connection.is_linked
            and tenant.telegram_connection.is_enabled
        ),
    }


def _filter_control_tenants(request, tenants):
    q = (request.GET.get("q") or "").strip().lower()
    status_filter = (request.GET.get("estado") or "").strip()
    type_filter = (request.GET.get("tipo") or "").strip()
    if q:
        tenants = [t for t in tenants if q in t.user.username.lower() or q in (t.business_name or "").lower()]
    if status_filter:
        tenants = [t for t in tenants if (
            (status_filter == "online" and t.is_online)
            or (status_filter == "active" and t.subscription_active)
            or (status_filter == "expired" and not t.subscription_active and not t.is_blocked)
            or (status_filter == "blocked" and t.is_blocked)
        )]
    if type_filter:
        tenants = [t for t in tenants if (type_filter == "demo") == t.is_demo]
    return tenants, {"q": q, "estado": status_filter, "tipo": type_filter}


@owner_required
def control_users(request):
    all_users = _control_tenant_rows(
        Tenant.objects.filter(is_demo=False).select_related("user")
    )
    users, filters = _filter_control_tenants(request, all_users)
    return render(request, "jheliztv/control/users.html", {
        "title": "Usuarios", "jc_control_active": "users",
        "tenants": users, "filters": filters, "kpi": _control_kpi(all_users),
    })


@owner_required
def control_demos(request):
    demos = _control_tenant_rows(
        Tenant.objects.filter(is_demo=True).select_related("user")
    )
    demos, filters = _filter_control_tenants(request, demos)
    return render(request, "jheliztv/control/demos.html", {
        "title": "Demos", "jc_control_active": "demos",
        "tenants": demos, "filters": filters,
    })


@owner_required
def control_payments(request):
    pending = list(
        TenantPayment.objects.filter(status=TenantPayment.Status.PENDING)
        .select_related("tenant", "tenant__user").order_by("-created_at")
    )
    return render(request, "jheliztv/control/payments.html", {
        "title": "Pagos", "jc_control_active": "payments", "pending": pending,
    })


@owner_required
@require_POST
def control_demo_create(request):
    now = timezone.now()
    expired_user_ids = list(
        Tenant.objects.filter(is_demo=True, plan_expires_at__lte=now)
        .values_list("user_id", flat=True)
    )
    if expired_user_ids:
        User.objects.filter(pk__in=expired_user_ids).delete()

    username = f"demo_{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(9)
    with transaction.atomic():
        user = User.objects.create_user(username=username, password=password)
        tenant = Tenant.objects.create(
            user=user,
            business_name="Demo JHELIZ CONTROL TV",
            plan_expires_at=now + timedelta(days=3),
            is_demo=True,
        )
        services = [
            Service.objects.create(owner=user, name="StreamPlus", icon="live_tv", color="#10b981"),
            Service.objects.create(owner=user, name="CineMax", icon="movie", color="#8b5cf6"),
        ]
        clients = [
            Client.objects.create(owner=user, name="Ana Torres", whatsapp="+51900000001"),
            Client.objects.create(owner=user, name="Carlos Ruiz", whatsapp="+51900000002"),
            Client.objects.create(owner=user, name="María López", whatsapp="+51900000003"),
        ]
        samples = [
            (clients[0], services[0], "demo-ana@example.com", 25, 10, 18),
            (clients[1], services[1], "demo-carlos@example.com", 30, 12, 3),
            (clients[2], services[0], "demo-maria@example.com", 25, 10, 1),
        ]
        for client, service, account, cost, investment, days in samples:
            subscription = Subscription.objects.create(
                owner=user, client=client, service=service,
                account_email=account, account_password="demo-segura",
                cost=Decimal(cost), investment=Decimal(investment),
                expires_at=now + timedelta(days=days),
            )
            for kind, amount, label in (
                (Transaction.Kind.INCOME, cost, "Venta"),
                (Transaction.Kind.EXPENSE, investment, "Costo"),
            ):
                Transaction.objects.create(
                    owner=user, kind=kind, amount=Decimal(amount),
                    description=f"{label} demo · {service.name}",
                    client=client, subscription=subscription,
                    occurred_at=now - timedelta(days=max(0, 18 - days)),
                )

    response = render(request, "jheliztv/control/demo_credentials.html", {
        "tenant": tenant,
        "demo_username": username,
        "demo_password": password,
        "login_url": request.build_absolute_uri(reverse("jheliztv_login")),
    })
    response["Cache-Control"] = "no-store, private"
    response["Pragma"] = "no-cache"
    return response


@owner_required
@require_POST
def control_payment_approve(request, pk):
    pay = get_object_or_404(TenantPayment, pk=pk)
    if pay.is_pending:
        pay.approve()
        messages.success(request, f"Pago de {pay.tenant} aprobado: +{pay.days} días de alquiler.")
    return redirect("jheliztv_control_payments")


@owner_required
@require_POST
def control_payment_reject(request, pk):
    pay = get_object_or_404(TenantPayment, pk=pk)
    if pay.is_pending:
        pay.reject("Rechazado desde el panel de control.")
        messages.warning(request, f"Pago de {pay.tenant} rechazado.")
    return redirect("jheliztv_control_payments")


@owner_required
def control_payment_proof(request, pk):
    pay = get_object_or_404(TenantPayment, pk=pk)
    if not pay.proof:
        return redirect("jheliztv_control_dashboard")
    response = FileResponse(pay.proof.open("rb"), content_type="application/octet-stream")
    response["Content-Disposition"] = f'inline; filename="comprobante-{pay.pk}.jpg"'
    response["Cache-Control"] = "no-store, private"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@owner_required
@require_POST
def control_tenant_extend(request, pk):
    tenant = get_object_or_404(Tenant, pk=pk)
    try:
        days = int(request.POST.get("days") or 30)
    except (TypeError, ValueError):
        days = 30
    tenant.extend(days)
    messages.success(request, f"{tenant}: +{days} días de alquiler.")
    return redirect("jheliztv_control_demos" if tenant.is_demo else "jheliztv_control_users")


@owner_required
@require_POST
def control_tenant_block(request, pk):
    """Bloquea/desbloquea al inquilino sin borrar sus datos."""
    tenant = get_object_or_404(Tenant, pk=pk)
    tenant.is_blocked = not tenant.is_blocked
    tenant.save(update_fields=["is_blocked"])
    if tenant.is_blocked:
        messages.warning(request, f"{tenant} fue bloqueado: ya no puede entrar (sus datos se conservan).")
    else:
        messages.success(request, f"{tenant} fue desbloqueado: ya puede entrar de nuevo.")
    return redirect("jheliztv_control_demos" if tenant.is_demo else "jheliztv_control_users")


@owner_required
@require_POST
def control_tenant_password_reset_link(request, pk):
    """Genera un enlace temporal para que el dueño se lo envíe al inquilino."""
    tenant = get_object_or_404(Tenant.objects.select_related("user"), pk=pk)
    uid = urlsafe_base64_encode(force_bytes(tenant.user.pk))
    token = default_token_generator.make_token(tenant.user)
    path = reverse("jheliztv_password_reset_confirm", kwargs={"uidb64": uid, "token": token})
    response = render(request, "jheliztv/control/password_reset_link.html", {"tenant": tenant, "reset_url": request.build_absolute_uri(path)})
    response["Cache-Control"] = "no-store, private"
    response["Pragma"] = "no-cache"
    return response
