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
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.tokens import default_token_generator
from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.security_events import record_security_event

from .models import (
    SaasSettings,
    Subscription,
    TelegramConnection,
    Tenant,
    TenantActivityEvent,
    TenantPayment,
)


def owner_required(view):
    """Exige el permiso global explícito del dueño de la plataforma."""

    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if not (
            request.user.is_authenticated
            and request.user.has_perm("gestion.manage_tenants")
        ):
            return redirect("jheliztv_control_login")
        from django_otp.plugins.otp_totp.models import TOTPDevice
        if TOTPDevice.objects.filter(user=request.user, name="Jheliz Control", confirmed=True).exists() and not request.session.get("jheliz_control_otp_verified"):
            request.session["jheliz_control_otp_pending_user"] = request.user.pk
            return redirect("jheliztv_control_2fa_verify")
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
        from django_otp.plugins.otp_totp.models import TOTPDevice
        if TOTPDevice.objects.filter(user=user, name="Jheliz Control", confirmed=True).exists():
            request.session["jheliz_control_otp_pending_user"] = user.pk
            request.session["jheliz_control_otp_backend"] = "django.contrib.auth.backends.ModelBackend"
            return redirect("jheliztv_control_2fa_verify")
        login(request, user)
        return redirect("jheliztv_control_dashboard")
    return render(request, "jheliztv/control/login.html", {})


def control_logout(request):
    logout(request)
    return redirect("jheliztv_control_login")


@owner_required
def control_dashboard(request):
    now = timezone.now()
    query = (request.GET.get("q") or "").strip()
    activity_filter = (request.GET.get("actividad") or "todos").strip()
    tenant_query = Tenant.objects.select_related("user", "activity").annotate(
        clients_count=Count("user__jc_clients", distinct=True),
        services_count=Count("user__jc_services", distinct=True),
        subscriptions_count=Count("user__jc_subscriptions", distinct=True),
    )
    if query:
        tenant_query = tenant_query.filter(
            Q(user__username__icontains=query)
            | Q(business_name__icontains=query)
            | Q(whatsapp__icontains=query)
        )
    if activity_filter == "online":
        tenant_query = tenant_query.filter(activity__last_seen_at__gte=now-timedelta(minutes=10))
    elif activity_filter == "semana":
        tenant_query = tenant_query.filter(activity__last_seen_at__gte=now-timedelta(days=7))
    elif activity_filter == "inactivos":
        tenant_query = tenant_query.filter(
            Q(activity__last_seen_at__lt=now-timedelta(days=30)) | Q(activity__isnull=True)
        )
    elif activity_filter == "vencidos":
        tenant_query = tenant_query.filter(Q(plan_expires_at__lte=now) | Q(plan_expires_at__isnull=True))
    elif activity_filter == "sin_telegram":
        tenant_query = tenant_query.filter(Q(user__jc_telegram_connection__chat_id__isnull=True) | Q(user__jc_telegram_connection__chat_id=""))
    tenants = list(tenant_query.order_by("-created_at"))
    pending = list(
        TenantPayment.objects.filter(status=TenantPayment.Status.PENDING)
        .select_related("tenant", "tenant__user")
        .order_by("-created_at")
    )
    telegram_by_owner = {
        connection.owner_id: connection
        for connection in TelegramConnection.objects.select_related("owner")
    }

    for t in tenants:
        t.telegram_connection = telegram_by_owner.get(t.user_id)
        if t.is_blocked:
            t.estado, t.estado_color = "Bloqueado", "red"
        elif t.subscription_active:
            t.estado, t.estado_color = "Activo", "green"
        else:
            t.estado, t.estado_color = "Vencido", "red"
        activity = getattr(t, "activity", None)
        t.last_seen_at = activity.last_seen_at if activity else None
        t.is_online = bool(t.last_seen_at and t.last_seen_at >= now-timedelta(minutes=10))
        t.activity_label = "En línea" if t.is_online else ("Nunca ingresó" if not t.last_seen_at else "Inactivo")

    all_tenants = Tenant.objects.select_related("activity")
    total = all_tenants.count()
    activos = sum(1 for t in all_tenants if t.subscription_active)
    online = sum(1 for t in all_tenants if getattr(t, "activity", None) and t.activity.last_seen_at >= now-timedelta(minutes=10))
    active_week = sum(1 for t in all_tenants if getattr(t, "activity", None) and t.activity.last_seen_at >= now-timedelta(days=7))
    inactive = total - sum(1 for t in all_tenants if getattr(t, "activity", None) and t.activity.last_seen_at >= now-timedelta(days=30))
    recent_events = TenantActivityEvent.objects.select_related("tenant", "tenant__user")[:12]
    ctx = {
        "title": "Control jheliztv",
        "tenants": tenants,
        "pending": pending,
        "query": query,
        "activity_filter": activity_filter,
        "recent_events": recent_events,
        "kpi": {
            "total": total,
            "activos": activos,
            "vencidos": total - activos,
            "pendientes": len(pending),
            "subs": Subscription.objects.filter(is_archived=False).count(),
            "telegram": sum(
                1
                for connection in telegram_by_owner.values()
                if connection.is_linked and connection.is_enabled
            ),
            "online": online,
            "active_week": active_week,
            "inactive": inactive,
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
    return redirect("jheliztv_control_dashboard")


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
    return redirect("jheliztv_control_dashboard")


@owner_required
@require_POST
def control_password_recovery(request):
    """Generate a short-lived link after the owner verifies the account holder."""
    username = (request.POST.get("username") or "").strip()
    tenant = (
        Tenant.objects.select_related("user")
        .filter(user__username__iexact=username)
        .first()
    )
    if tenant is None:
        messages.error(request, "No se encontró un usuario con ese nombre exacto.")
        return redirect("jheliztv_control_dashboard")
    if not tenant.user.is_active:
        messages.error(request, "El usuario seleccionado está inactivo.")
        return redirect("jheliztv_control_dashboard")

    from .tenant_views import password_recovery_token_generator

    uid = urlsafe_base64_encode(force_bytes(tenant.user.pk))
    token = password_recovery_token_generator.make_token(tenant.user)
    base_url = getattr(
        settings, "JHELIZ_CONTROL_BASE_URL", "https://jheliztv.xyz"
    ).rstrip("/")
    recovery_url = f"{base_url}/recuperar/{uid}/{token}/"
    record_security_event(
        "account.password_recovery_link_generated",
        severity="warning",
        request=request,
        actor=request.user,
        username=tenant.user.get_username(),
        metadata={"target_user_id": tenant.user_id, "tenant_id": tenant.pk},
    )
    return render(
        request,
        "jheliztv/control/password_recovery_link.html",
        {"tenant": tenant, "recovery_url": recovery_url},
    )


@owner_required
@require_POST
def control_tenant_password_reset_link(request, pk):
    """Genera un enlace temporal para que el dueño se lo envíe al inquilino."""
    tenant = get_object_or_404(Tenant.objects.select_related("user"), pk=pk)
    uid = urlsafe_base64_encode(force_bytes(tenant.user.pk))
    token = default_token_generator.make_token(tenant.user)
    path = reverse(
        "jheliztv_password_reset_confirm",
        kwargs={"uidb64": uid, "token": token},
    )
    response = render(
        request,
        "jheliztv/control/password_reset_link.html",
        {"tenant": tenant, "reset_url": request.build_absolute_uri(path)},
    )
    response["Cache-Control"] = "no-store, private"
    response["Pragma"] = "no-cache"
    return response


def control_2fa_verify(request):
    uid = request.session.get("jheliz_control_otp_pending_user")
    if not uid:
        return redirect("jheliztv_control_login")
    user = get_user_model().objects.filter(pk=uid, is_active=True).first()
    if not user or not user.has_perm("gestion.manage_tenants"):
        return redirect("jheliztv_control_login")
    if request.method == "POST":
        token = (request.POST.get("token") or "").strip()
        from django_otp.plugins.otp_totp.models import TOTPDevice
        from django_otp.plugins.otp_static.models import StaticDevice
        valid = any(d.verify_token(token) for d in TOTPDevice.objects.filter(user=user, name="Jheliz Control", confirmed=True))
        if not valid:
            valid = any(d.verify_token(token) for d in StaticDevice.objects.filter(user=user, confirmed=True))
        if valid:
            login(request, user, backend=request.session.pop("jheliz_control_otp_backend", "django.contrib.auth.backends.ModelBackend"))
            request.session.pop("jheliz_control_otp_pending_user", None)
            request.session["jheliz_control_otp_verified"] = True
            return redirect("jheliztv_control_dashboard")
        messages.error(request, "Código 2FA incorrecto o vencido.")
    return render(request, "jheliztv/control/2fa_verify.html")


@owner_required
def control_2fa_setup(request):
    from django_otp.plugins.otp_totp.models import TOTPDevice
    user=request.user
    confirmed=TOTPDevice.objects.filter(user=user, name="Jheliz Control", confirmed=True).first()
    pending=TOTPDevice.objects.filter(user=user, confirmed=False).order_by("-id").first()
    if request.method == "POST" and request.POST.get("action") == "create":
        TOTPDevice.objects.filter(user=user, confirmed=False).delete()
        TOTPDevice.objects.create(user=user, name="Jheliz Control", confirmed=False)
        return redirect("jheliztv_control_2fa_setup")
    if request.method == "POST" and request.POST.get("action") == "verify" and pending:
        if pending.verify_token((request.POST.get("token") or "").strip()):
            pending.confirmed=True; pending.save(update_fields=["confirmed"]); request.session["jheliz_control_otp_verified"]=True
            messages.success(request,"2FA activado correctamente para Jheliz Control.")
            return redirect("jheliztv_control_dashboard")
        messages.error(request,"El código no coincide.")
    secret=uri=None
    if pending:
        uri=pending.config_url
        from urllib.parse import parse_qs, urlparse
        secret=(parse_qs(urlparse(uri).query).get("secret") or [None])[0]
    return render(request,"jheliztv/control/2fa_setup.html",{"confirmed":confirmed,"pending":pending,"secret":secret,"uri":uri})
