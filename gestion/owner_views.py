"""Panel del **dueño/proveedor** de jheliztv.xyz, montado en ``/control/``.

Separado de la web del inquilino (``tenant_views``) y del admin de la tienda
(``/panel-jheliz-2026/``). Solo accede el **staff** (el dueño): desde acá ve los
inquilinos registrados en jheliztv.xyz, controla su alquiler (suscripción) y
aprueba/rechaza los pagos Yape — sin tocar la tienda.

Vive bajo ``config.urls_jheliztv`` (solo se sirve en el dominio jheliztv.xyz),
así que el futuro dueño de la tienda no lo ve desde su propio dominio.
"""
from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import SaasSettings, Subscription, Tenant, TenantPayment


def owner_required(view):
    """Exige sesión iniciada de un usuario **staff** (el dueño)."""

    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_staff):
            return redirect("jheliztv_control_login")
        return view(request, *args, **kwargs)

    return _wrapped


def control_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("jheliztv_control_dashboard")
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        user = authenticate(request, username=username, password=password)
        if user is None or not user.is_staff:
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
    tenants = list(Tenant.objects.select_related("user").order_by("-created_at"))
    pending = list(
        TenantPayment.objects.filter(status=TenantPayment.Status.PENDING)
        .select_related("tenant", "tenant__user")
        .order_by("-created_at")
    )

    for t in tenants:
        if t.is_blocked:
            t.estado, t.estado_color = "Bloqueado", "red"
        elif t.subscription_active:
            t.estado, t.estado_color = "Activo", "green"
        else:
            t.estado, t.estado_color = "Vencido", "red"

    total = len(tenants)
    activos = sum(1 for t in tenants if t.subscription_active)
    ctx = {
        "title": "Control jheliztv",
        "tenants": tenants,
        "pending": pending,
        "kpi": {
            "total": total,
            "activos": activos,
            "vencidos": total - activos,
            "pendientes": len(pending),
            "subs": Subscription.objects.filter(is_archived=False).count(),
        },
        "saas": SaasSettings.load(),
    }
    return render(request, "jheliztv/control/dashboard.html", ctx)


@owner_required
@require_POST
def control_payment_approve(request, pk):
    pay = get_object_or_404(TenantPayment, pk=pk)
    if pay.is_pending:
        pay.approve()
        messages.success(request, f"Pago de {pay.tenant} aprobado: +{pay.days} días de alquiler.")
    return redirect("jheliztv_control_dashboard")


@owner_required
@require_POST
def control_payment_reject(request, pk):
    pay = get_object_or_404(TenantPayment, pk=pk)
    if pay.is_pending:
        pay.reject("Rechazado desde el panel de control.")
        messages.warning(request, f"Pago de {pay.tenant} rechazado.")
    return redirect("jheliztv_control_dashboard")


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
    return redirect("jheliztv_control_dashboard")
