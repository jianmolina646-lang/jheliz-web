"""Web del **inquilino** de Jheliz Control (producto SaaS en jheliztv.xyz).

A diferencia de ``views.py`` (que vive dentro del panel admin y usa
``@staff_member_required``), estas vistas son la cara pública del producto que
se **alquila**: cada inquilino entra con su propio usuario/contraseña y ve solo
sus datos. El cobro del alquiler es por **Yape con aprobación manual**.

Reutiliza el mismo diseño "Jheliz Control" (clases ``jc-*``) mediante templates
standalone bajo ``templates/jheliztv/`` (no dependen del admin).
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import secrets
from urllib.parse import quote
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import get_user_model
from django.db.models import Prefetch, Q, Sum
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from config.date_utils import add_service_duration
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .forms import ClientForm, ControlSettingsForm, ServiceForm, SubscriptionForm, TransactionForm
from .currencies import CURRENCIES, currency_symbol, normalize_currency
from .control_operations import (
    create_client,
    create_subscription,
    delete_client as delete_client_operation,
    renew_subscription as renew_subscription_operation,
    update_client,
)
from .models import (
    Client,
    ControlSettings,
    SaasSettings,
    Service,
    ServiceCategory,
    StockEmail,
    Subscription,
    SupportContact,
    SupportMessage,
    SupportTicket,
    RenewalRequest,
    ResellerPaymentMethod,
    Tenant,
    TenantPayment,
    TelegramConnection,
    Transaction,
    WhatsAppConnection,
)
from .whatsapp import MetaAPIError, finish_signup, process_webhook, verify_signature
from .views import _decorate_subs  # reuso de helpers
from .support_operations import add_message as add_support_message, set_status as set_support_status

User = get_user_model()


# ---------------------------------------------------------------------------
# Acceso
# ---------------------------------------------------------------------------
def _get_tenant(user):
    if not user.is_authenticated:
        return None
    return Tenant.objects.filter(user=user).first()


def tenant_required(view):
    """Exige login + suscripción de alquiler vigente.

    Si el inquilino no pagó (o venció), lo manda a "Mi suscripción".
    """
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        tenant = _get_tenant(request.user)
        if tenant is None:
            return redirect("jheliztv_login")
        if not tenant.subscription_active:
            messages.warning(
                request,
                "Tu suscripción está vencida. Renueva para seguir usando Jheliz Control.",
            )
            return redirect("jheliztv_billing")
        return view(request, tenant, *args, **kwargs)

    return _wrapped


def _days_left(tenant):
    if not tenant or not tenant.plan_expires_at:
        return None
    delta = tenant.plan_expires_at - timezone.now()
    return max(0, delta.days)


def _ctx(request, tenant, **extra):
    owner = request.user
    settings_obj = ControlSettings.load(owner)
    base = {
        "jc_settings": settings_obj,
        "jc_currency": settings_obj.currency,
        "jc_currency_symbol": currency_symbol(settings_obj.currency),
        "jc_currencies": CURRENCIES,
        "jc_tenant": tenant,
        "jc_days_left": _days_left(tenant),
        "jc_alerts": _expiry_alerts(owner),
        **extra,
    }
    return base


def _expiry_alerts(owner, within_days: int = 3):
    now = timezone.now()
    soon = now + timedelta(days=within_days)
    return list(
        Subscription.objects.filter(owner=owner, is_archived=False, expires_at__lte=soon)
        .select_related("client", "service")
        .order_by("expires_at")
    )


# ---------------------------------------------------------------------------
# Landing + auth
# ---------------------------------------------------------------------------
def _public_renewal_render(request, context, status=200):
    response = render(request, "jheliztv/public_renewal.html", context, status=status)
    response["Cache-Control"] = "no-store, private"
    response["Pragma"] = "no-cache"
    response["Referrer-Policy"] = "no-referrer"
    return response


def public_renewal(request, token):
    renewal = get_object_or_404(
        RenewalRequest.objects.select_related(
            "owner__jc_tenant", "subscription__client", "subscription__service"
        ),
        token=token,
    )
    sub = renewal.subscription
    methods = ResellerPaymentMethod.objects.filter(owner=renewal.owner, is_active=True)
    control = ControlSettings.load(renewal.owner)
    seller_phone = _international_phone(renewal.owner.jc_tenant.whatsapp, control.country)
    base_context = {
        "renewal": renewal, "sub": sub, "methods": methods,
        "business": renewal.owner.jc_tenant.business_name or renewal.owner.username,
        "seller_phone": seller_phone,
    }
    if renewal.link_expired:
        return _public_renewal_render(request, {**base_context, "expired": True}, status=410)
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "renew":
            renewal.status = RenewalRequest.Status.PAYMENT_PENDING
            renewal.requested_at = timezone.now()
            renewal.save(update_fields=["status", "requested_at", "updated_at"])
        elif action == "decline":
            renewal.status = RenewalRequest.Status.DECLINED
            renewal.requested_at = timezone.now()
            renewal.save(update_fields=["status", "requested_at", "updated_at"])
        elif action == "help":
            renewal.status = RenewalRequest.Status.HELP
            renewal.customer_note = (request.POST.get("note") or "")[:500]
            renewal.requested_at = timezone.now()
            renewal.save(update_fields=["status", "customer_note", "requested_at", "updated_at"])
        elif action == "proof":
            method = methods.filter(pk=request.POST.get("payment_method")).first()
            proof = request.FILES.get("proof")
            if not method or not proof:
                return _public_renewal_render(request, {
                    **base_context, "error": "Selecciona el método y adjunta el comprobante.",
                })
            if proof.size > 8 * 1024 * 1024 or not proof.content_type.startswith("image/"):
                return _public_renewal_render(request, {
                    **base_context, "error": "El comprobante debe ser JPG, PNG o WebP de máximo 8 MB.",
                })
            renewal.payment_method = method
            renewal.proof = proof
            renewal.customer_note = (request.POST.get("note") or "")[:500]
            renewal.status = RenewalRequest.Status.PROOF_SENT
            renewal.save()
        return redirect("jheliztv_public_renewal", token=renewal.token)
    return _public_renewal_render(request, base_context)


def landing(request):
    if _get_tenant(request.user):
        return redirect("jheliztv_dashboard")
    saas = SaasSettings.load()
    return render(request, "jheliztv/landing.html", {"saas": saas})


def register(request):
    if request.user.is_authenticated:
        return redirect("jheliztv_dashboard")
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        email = (request.POST.get("email") or "").strip()
        business = (request.POST.get("business_name") or "").strip()
        whatsapp = (request.POST.get("whatsapp") or "").strip()
        password = request.POST.get("password") or ""
        password2 = request.POST.get("password2") or ""

        errors = []
        if not username:
            errors.append("Elegí un usuario.")
        if User.objects.filter(username__iexact=username).exists():
            errors.append("Ese usuario ya existe, probá con otro.")
        if len(password) < 6:
            errors.append("La contraseña debe tener al menos 6 caracteres.")
        if password != password2:
            errors.append("Las contraseñas no coinciden.")

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(
                request, "jheliztv/register.html",
                {"form_data": request.POST},
            )

        user = User.objects.create_user(
            username=username, email=email, password=password,
        )
        tenant = Tenant.objects.create(
            user=user, business_name=business, whatsapp=whatsapp,
        )
        tenant.start_trial()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(
            request,
            f"¡Cuenta creada! Tenés {Tenant.TRIAL_DAYS} días de prueba gratis. 🎉",
        )
        return redirect("jheliztv_dashboard")

    return render(request, "jheliztv/register.html", {})


def login_view(request):
    if request.user.is_authenticated and _get_tenant(request.user):
        return redirect("jheliztv_dashboard")
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        user = authenticate(request, username=username, password=password)
        if user is None:
            messages.error(request, "Usuario o contraseña incorrectos.")
            return render(request, "jheliztv/login.html", {"username": username})
        tenant = _get_tenant(user)
        if tenant is None:
            # Un usuario de la tienda que no es inquilino: lo creamos al vuelo.
            tenant = Tenant.objects.create(user=user)
            tenant.start_trial()
        login(request, user)
        return redirect("jheliztv_dashboard")
    return render(request, "jheliztv/login.html", {})


def logout_view(request):
    logout(request)
    return redirect("jheliztv_landing")


# ---------------------------------------------------------------------------
# Cobro (Yape, aprobación manual)
# ---------------------------------------------------------------------------
def billing(request):
    tenant = _get_tenant(request.user)
    if tenant is None:
        return redirect("jheliztv_login")
    saas = SaasSettings.load()
    pending = tenant.payments.filter(status=TenantPayment.Status.PENDING).first()
    last_rejected = (
        tenant.payments.filter(status=TenantPayment.Status.REJECTED)
        .order_by("-created_at")
        .first()
    )
    ctx = {
        "jc_tenant": tenant,
        "jc_active": "billing",
        "jc_days_left": _days_left(tenant),
        "title": "Mi suscripción",
        "saas": saas,
        "pending": pending,
        "last_rejected": last_rejected,
        "payments": tenant.payments.all()[:10],
    }
    return render(request, "jheliztv/billing.html", ctx)


@require_POST
def billing_upload(request):
    tenant = _get_tenant(request.user)
    if tenant is None:
        return redirect("jheliztv_login")
    saas = SaasSettings.load()
    proof = request.FILES.get("proof")
    if not proof:
        messages.error(request, "Adjuntá la captura del pago por Yape.")
        return redirect("jheliztv_billing")
    if tenant.payments.filter(status=TenantPayment.Status.PENDING).exists():
        messages.info(request, "Ya tenés un pago pendiente de revisión.")
        return redirect("jheliztv_billing")
    TenantPayment.objects.create(
        tenant=tenant,
        amount=saas.monthly_price,
        days=30,
        proof=proof,
    )
    messages.success(
        request,
        "¡Comprobante recibido! Lo revisamos y activamos tu cuenta en breve.",
    )
    return redirect("jheliztv_billing")


# ---------------------------------------------------------------------------
# Panel del inquilino (Inicio)
# ---------------------------------------------------------------------------
@tenant_required
def dashboard(request, tenant):
    owner = request.user
    now = timezone.now()
    total_clients = Client.objects.filter(owner=owner).count()

    series, months = [], []
    y, mo = now.year, now.month
    for _ in range(6):
        months.append((y, mo))
        mo -= 1
        if mo == 0:
            mo, y = 12, y - 1
    months.reverse()

    max_val = Decimal("1")
    for (yy, mm) in months:
        income = (
            Transaction.objects.filter(
                owner=owner, kind=Transaction.Kind.INCOME,
                occurred_at__year=yy, occurred_at__month=mm,
            ).aggregate(s=Sum("base_amount"))["s"] or Decimal("0")
        )
        expense = (
            Transaction.objects.filter(
                owner=owner, kind=Transaction.Kind.EXPENSE,
                occurred_at__year=yy, occurred_at__month=mm,
            ).aggregate(s=Sum("base_amount"))["s"] or Decimal("0")
        )
        max_val = max(max_val, income, expense)
        label = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep",
                 "Oct", "Nov", "Dic"][mm - 1]
        series.append({"label": label, "income": income, "expense": expense})
    for row in series:
        row["income_pct"] = int(round(float(row["income"]) / float(max_val) * 100))
        row["expense_pct"] = int(round(float(row["expense"]) / float(max_val) * 100))

    total_income = (
        Transaction.objects.filter(owner=owner, kind=Transaction.Kind.INCOME)
        .aggregate(s=Sum("base_amount"))["s"] or Decimal("0")
    )
    total_expense = (
        Transaction.objects.filter(owner=owner, kind=Transaction.Kind.EXPENSE)
        .aggregate(s=Sum("base_amount"))["s"] or Decimal("0")
    )
    active_subs = Subscription.objects.filter(owner=owner, is_archived=False).count()

    ctx = _ctx(
        request, tenant,
        title="Inicio", jc_active="dashboard",
        total_clients=total_clients, active_subs=active_subs,
        series=series, total_income=total_income, total_expense=total_expense,
        net=total_income - total_expense,
    )
    return render(request, "jheliztv/dashboard.html", ctx)


# ---------------------------------------------------------------------------
# Servicios
# ---------------------------------------------------------------------------
@tenant_required
def services_board(request, tenant):
    owner = request.user
    categories = ServiceCategory.objects.prefetch_related("services").all()
    cats = []
    for c in categories:
        svcs = list(c.services.filter(owner=owner))
        if svcs:
            cats.append({"cat": c, "services": svcs})
    uncategorized = list(Service.objects.filter(owner=owner, category__isnull=True))
    ctx = _ctx(
        request, tenant,
        title="Servicios", jc_active="services",
        categories=cats, uncategorized=uncategorized,
        form=ServiceForm(), all_categories=ServiceCategory.objects.all(),
    )
    return render(request, "jheliztv/services.html", ctx)


@tenant_required
@require_POST
def service_add(request, tenant):
    form = ServiceForm(request.POST, request.FILES)
    if form.is_valid():
        svc = form.save(commit=False)
        svc.owner = request.user
        svc.save()
        messages.success(request, "Servicio agregado.")
    else:
        messages.error(request, "Revisá los datos del servicio.")
    return redirect("jheliztv_services")


@tenant_required
@require_POST
def service_edit(request, tenant, pk):
    service = get_object_or_404(Service, pk=pk, owner=request.user)
    form = ServiceForm(request.POST, request.FILES, instance=service)
    if form.is_valid():
        form.save()
        messages.success(request, "Servicio actualizado.")
    else:
        messages.error(request, "Revisá los datos del servicio.")
    return redirect("jheliztv_service_detail", pk=service.pk)


@tenant_required
@require_POST
def service_delete(request, tenant, pk):
    get_object_or_404(Service, pk=pk, owner=request.user).delete()
    messages.success(request, "Servicio eliminado.")
    return redirect("jheliztv_services")


@tenant_required
def service_detail(request, tenant, pk):
    owner = request.user
    service = get_object_or_404(Service, pk=pk, owner=owner)
    subs = _decorate_subs(
        list(service.subscriptions.filter(is_archived=False).select_related("client"))
    )
    control = ControlSettings.load(owner)
    business = tenant.business_name or owner.username
    for sub in subs:
        renewal = _renewal_request_for(sub)
        public_url = request.build_absolute_uri(
            reverse("jheliztv_public_renewal", kwargs={"token": renewal.token})
        )
        phone = _international_phone(sub.client.whatsapp, control.country)
        sub.renewal_phone = f"+{phone}" if phone else ""
        expiry = timezone.localtime(sub.expires_at).strftime("%d/%m/%Y")
        text = (
            f"Hola {sub.client.name} 👋\n\nTu servicio está próximo a vencer.\n\n"
            f"📺 Plataforma: {sub.service.name}\n📧 Correo: {_masked_account(sub.account_email)}\n"
            f"📅 Vencimiento: {expiry}\n\n¿Deseas renovar? Confirma aquí:\n{public_url}\n\n"
            f"Gracias por confiar en {business}."
        )
        sub.renewal_url = public_url
        sub.renewal_whatsapp_link = f"https://wa.me/{phone}?text={quote(text)}" if phone else ""
    # KPIs del servicio (estilo KINEMANAGER).
    ingresos = sum((s.cost * s.exchange_rate for s in subs), Decimal("0"))
    egresos = sum((s.investment * s.exchange_rate for s in subs), Decimal("0"))
    n_clients = len({s.client_id for s in subs})
    form = SubscriptionForm(initial={"service": service})
    form.fields["client"].queryset = Client.objects.filter(owner=owner)
    ctx = _ctx(
        request, tenant,
        title=service.name, jc_active="services",
        service=service, subs=subs, form=form,
        kpi_ingresos=ingresos, kpi_egresos=egresos, kpi_clients=n_clients,
        clients=Client.objects.filter(owner=owner),
        all_categories=ServiceCategory.objects.all(),
    )
    return render(request, "jheliztv/service_detail.html", ctx)


# ---------------------------------------------------------------------------
# Suscripciones
# ---------------------------------------------------------------------------
def _split_emails(raw: str) -> list[str]:
    """Separa correos por coma/; /salto de línea y elimina duplicados."""
    parts = re.split(r"[,;\n]+", raw or "")
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        e = p.strip()
        if e and e.lower() not in seen:
            seen.add(e.lower())
            out.append(e)
    return out


def _dec(value) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")


def _parse_expires_on(raw):
    """Convierte una fecha ``YYYY-MM-DD`` (input type=date) en el datetime de
    vencimiento (fin de ese día, en la zona horaria activa). Devuelve ``None``
    si no hay fecha válida, para que se use ``duration_days`` en su lugar."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        d = datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    naive = datetime.combine(d, time(23, 59))
    return timezone.make_aware(naive, timezone.get_current_timezone())


@tenant_required
@require_POST
def subscription_add(request, tenant):
    owner = request.user
    post = request.POST
    service = get_object_or_404(Service, pk=post.get("service") or 0, owner=owner)

    # --- Cliente: usar uno existente o crear uno nuevo al vuelo ---------------
    client = None
    client_id = (post.get("client") or "").strip()
    if client_id:
        client = Client.objects.filter(pk=client_id, owner=owner).first()
    if client is None:
        new_name = (post.get("new_client_name") or "").strip()
        if new_name:
            client = Client.objects.create(
                owner=owner, name=new_name,
                whatsapp=(post.get("new_client_whatsapp") or "").strip(),
                telegram=(post.get("new_client_telegram") or "").strip(),
            )
    if client is None:
        messages.error(request, "Elegí un cliente o cargá uno nuevo.")
        return redirect("jheliztv_service_detail", pk=service.pk)

    # --- Correos (uno o varios separados por coma) ----------------------------
    emails = _split_emails(post.get("account_emails") or post.get("account_email") or "")
    if not emails:
        messages.error(request, "Ingresá al menos un correo de la cuenta.")
        return redirect("jheliztv_service_detail", pk=service.pk)

    password = (post.get("account_password") or "").strip()
    plan = Subscription.Plan.COMPLETA if post.get("plan") == "completa" else Subscription.Plan.PERFIL
    try:
        profiles = max(1, min(7, int(post.get("profiles") or 1)))
    except (TypeError, ValueError):
        profiles = 1
    if plan == Subscription.Plan.COMPLETA:
        profiles = 1
    plan_label = (post.get("plan_label") or "").strip()
    profile_name = (post.get("profile_name") or "").strip()
    profile_pin = (post.get("profile_pin") or "").strip()

    starts = timezone.now()
    # El tiempo del servicio se puede dar por "días" (duration_days) o eligiendo
    # directamente la fecha de vencimiento (expires_on, formato YYYY-MM-DD).
    expires = _parse_expires_on(post.get("expires_on"))
    if expires is None:
        try:
            days = max(1, int(post.get("duration_days") or 30))
        except (TypeError, ValueError):
            days = 30
        expires = add_service_duration(starts, days)
    # Los totales ("¿cuánto vendiste/invertiste en total?") se reparten en
    # partes iguales entre los correos cargados.
    n = len(emails)
    cost_each = (_dec(post.get("cost")) / n).quantize(Decimal("0.01"))
    inv_each = (_dec(post.get("investment")) / n).quantize(Decimal("0.01"))
    base_currency = normalize_currency(ControlSettings.load(owner).currency)
    payment_currency = normalize_currency(post.get("currency") or base_currency)
    if payment_currency != base_currency and _dec(post.get("exchange_rate")) <= 0:
        messages.error(request, f"Ingresa el tipo de cambio de {payment_currency} a {base_currency}.")
        return redirect("jheliztv_service_detail", pk=service.pk)

    for email in emails:
        create_subscription(
            owner,
            {
                "client_id": client.pk,
                "service_id": service.pk,
                "account_email": email,
                "account_password": password,
                "plan": plan,
                "profiles": profiles,
                "profile_name": profile_name,
                "profile_pin": profile_pin,
                "plan_label": plan_label,
                "cost": cost_each,
                "investment": inv_each,
                "currency": post.get("currency"),
                "exchange_rate": post.get("exchange_rate"),
                "starts_at": starts,
                "expires_at": expires,
            },
        )

    if n == 1:
        messages.success(request, "Suscripción creada.")
    else:
        messages.success(request, f"Se crearon {n} suscripciones.")
    return redirect("jheliztv_service_detail", pk=service.pk)


@tenant_required
def subscription_edit(request, tenant, pk):
    sub = get_object_or_404(Subscription, pk=pk, owner=request.user)
    # Los navegadores móviles pueden restaurar o recargar la URL final de un
    # formulario POST. En ese caso no mostramos un 405: volvemos a la vista
    # segura desde la que se abre el modal de edición.
    if request.method != "POST":
        return redirect("jheliztv_service_detail", pk=sub.service_id)
    # Al editar no se cambian cliente ni servicio: los tomamos de la propia
    # suscripción (el modal no los reenvía y antes mandaba "client" vacío).
    data = request.POST.copy()
    data["client"] = sub.client_id
    data["service"] = sub.service_id
    form = SubscriptionForm(data, instance=sub)
    if form.is_valid():
        form.save()
        messages.success(request, "Suscripción actualizada.")
    else:
        messages.error(request, "No se pudo actualizar la suscripción.")
    return redirect("jheliztv_service_detail", pk=sub.service_id)


@tenant_required
@require_POST
def subscription_renew(request, tenant, pk):
    sub = get_object_or_404(Subscription, pk=pk, owner=request.user)
    service_id = sub.service_id
    expires = _parse_expires_on(request.POST.get("expires_on"))
    if expires is not None:
        # Renovación "por fecha": el vencimiento queda exactamente ese día.
        sub.expires_at = expires
        sub.save(update_fields=["expires_at"])
        messages.success(
            request,
            f"Renovada. Nuevo vencimiento: {timezone.localtime(sub.expires_at):%d/%m/%Y}.",
        )
        return redirect("jheliztv_service_detail", pk=sub.service_id)
    try:
        days = int(request.POST.get("days", 30))
    except (TypeError, ValueError):
        days = 30
    sub, error = renew_subscription_operation(request.user, pk, days)
    if error:
        messages.error(request, "No se pudo renovar la suscripción.")
        return redirect("jheliztv_service_detail", pk=service_id)
    messages.success(
        request,
        f"Renovada +{days} días. Nuevo vencimiento: "
        f"{timezone.localtime(sub.expires_at):%d/%m/%Y}.",
    )
    return redirect("jheliztv_service_detail", pk=sub.service_id)


@tenant_required
@require_POST
def subscription_delete(request, tenant, pk):
    sub = get_object_or_404(Subscription, pk=pk, owner=request.user)
    service_id = sub.service_id
    sub.delete()
    messages.success(request, "Suscripción eliminada.")
    return redirect("jheliztv_service_detail", pk=service_id)


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------
@tenant_required
def clients(request, tenant):
    owner = request.user
    active_subs_qs = (
        Subscription.objects.filter(is_archived=False)
        .select_related("service")
        .order_by("expires_at")
    )
    qs = Client.objects.filter(owner=owner).prefetch_related(
        Prefetch("subscriptions", queryset=active_subs_qs, to_attr="active_subs")
    )
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(telegram__icontains=q)
            | Q(email__icontains=q) | Q(whatsapp__icontains=q)
            | Q(subscriptions__account_email__icontains=q)
        ).distinct()

    clients = list(qs)
    sort = (request.GET.get("sort") or "expiry").strip()
    if sort == "name":
        clients.sort(key=lambda c: c.name.lower())
    elif sort == "active":
        clients.sort(key=lambda c: (-len(c.active_subs), c.name.lower()))
    else:  # "expiry": primero lo que vence antes; sin suscripciones activas al final
        sort = "expiry"
        far = timezone.now() + timedelta(days=3650)
        clients.sort(
            key=lambda c: (min((s.expires_at for s in c.active_subs), default=far), c.name.lower())
        )

    # Agrupar las suscripciones por servicio (para el modal "Extraer a PDF").
    for c in clients:
        groups: dict[int, dict] = {}
        for s in c.active_subs:
            g = groups.setdefault(
                s.service_id, {"service": s.service, "count": 0}
            )
            g["count"] += 1
        c.svc_groups = sorted(groups.values(), key=lambda g: g["service"].name.lower())

    ctx = _ctx(
        request, tenant,
        title="Mis clientes", jc_active="clients",
        clients=clients, form=ClientForm(), q=q, sort=sort,
    )
    return render(request, "jheliztv/clients.html", ctx)


@tenant_required
@require_POST
def client_add(request, tenant):
    client, error = create_client(request.user, request.POST)
    if not error:
        messages.success(request, "Cliente agregado.")
    else:
        messages.error(request, "Revisá los datos del cliente.")
    return redirect("jheliztv_clients")


@tenant_required
@require_POST
def client_edit(request, tenant, pk):
    get_object_or_404(Client, pk=pk, owner=request.user)
    client, error = update_client(request.user, pk, request.POST)
    if not error:
        messages.success(request, "Cliente actualizado.")
    else:
        messages.error(request, "No se pudo actualizar el cliente.")
    return redirect("jheliztv_clients")


@tenant_required
@require_POST
def client_delete(request, tenant, pk):
    get_object_or_404(Client, pk=pk, owner=request.user)
    deleted, error = delete_client_operation(request.user, pk)
    if deleted:
        messages.success(request, "Cliente eliminado.")
    else:
        messages.error(request, "No se pudo eliminar el cliente.")
    return redirect("jheliztv_clients")


@tenant_required
def client_report_pdf(request, tenant, pk):
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    client = get_object_or_404(Client, pk=pk, owner=request.user)
    subs_qs = client.subscriptions.filter(is_archived=False).select_related("service")
    # "Extraer": permite elegir qué servicios incluir
    # (?services=1&services=2 o ?services=1,2,3).
    raw = " ".join(request.GET.getlist("services")).replace(",", " ")
    ids = [int(x) for x in raw.split() if x.isdigit()]
    if ids:
        subs_qs = subs_qs.filter(service_id__in=ids)
    subs = list(subs_qs.order_by("service__name", "account_email"))

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    green = colors.HexColor("#10b981")
    dark = colors.HexColor("#1f2937")

    c.setFillColor(green)
    c.rect(0, height - 30 * mm, width, 30 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(20 * mm, height - 18 * mm, "Jheliz Control")
    c.setFont("Helvetica", 11)
    c.drawString(20 * mm, height - 25 * mm, "Reporte de servicios del cliente")

    y = height - 42 * mm
    c.setFillColor(dark)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, y, client.name)
    y -= 7 * mm
    c.setFont("Helvetica", 10)
    contacto = []
    if client.telegram:
        contacto.append(f"Telegram: {client.telegram}")
    if client.whatsapp:
        contacto.append(f"WhatsApp: {client.whatsapp}")
    if client.email:
        contacto.append(f"Correo: {client.email}")
    if contacto:
        c.drawString(20 * mm, y, "  ·  ".join(contacto))
        y -= 6 * mm
    c.drawString(20 * mm, y, f"Generado: {timezone.localtime():%d/%m/%Y %H:%M}")
    y -= 10 * mm

    c.setFillColor(green)
    c.rect(20 * mm, y - 2 * mm, width - 40 * mm, 8 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(22 * mm, y, "Servicio")
    c.drawString(58 * mm, y, "Correo / usuario")
    c.drawString(112 * mm, y, "Clave")
    c.drawString(150 * mm, y, "Plan")
    c.drawString(172 * mm, y, "Vence")
    y -= 10 * mm

    c.setFont("Helvetica", 9)
    c.setFillColor(dark)
    if not subs:
        c.drawString(22 * mm, y, "Este cliente no tiene servicios activos.")
        y -= 8 * mm
    for s in subs:
        if y < 25 * mm:
            c.showPage()
            y = height - 30 * mm
        c.drawString(22 * mm, y, s.service.name[:20])
        c.drawString(58 * mm, y, s.account_email[:30])
        c.drawString(112 * mm, y, (s.account_password or "—")[:22])
        c.drawString(150 * mm, y, s.get_plan_display()[:11])
        c.drawString(172 * mm, y, timezone.localtime(s.expires_at).strftime("%d/%m/%Y"))
        y -= 7 * mm

    c.setFillColor(colors.HexColor("#9ca3af"))
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 12 * mm, "Jheliz Control · documento informativo")
    c.showPage()
    c.save()
    buf.seek(0)

    resp = HttpResponse(buf.getvalue(), content_type="application/pdf")
    fname = f"reporte-{client.name.lower().replace(' ', '-')}.pdf"
    resp["Content-Disposition"] = f'inline; filename="{fname}"'
    return resp


# ---------------------------------------------------------------------------
# Correos en stock (disponibilidad por plataforma)
# ---------------------------------------------------------------------------
def _international_phone(raw, country):
    import phonenumbers

    value = (raw or "").strip()
    if not value:
        return ""
    try:
        parsed = phonenumbers.parse(value, None if value.startswith("+") else country)
    except phonenumbers.NumberParseException:
        return ""
    if not phonenumbers.is_possible_number(parsed):
        return ""
    return phonenumbers.format_number(
        parsed, phonenumbers.PhoneNumberFormat.E164
    ).lstrip("+")


def _masked_account(value):
    value = (value or "").strip()
    if "@" not in value:
        return value[:3] + "•••"
    local, domain = value.split("@", 1)
    return f"{local[:3]}•••@{domain}"


def _renewal_request_for(sub):
    return RenewalRequest.objects.get_or_create(
        owner=sub.owner,
        subscription=sub,
        expiry_date=timezone.localtime(sub.expires_at).date(),
    )[0]


@tenant_required
def stock_emails(request, tenant):
    owner = request.user
    qs = StockEmail.objects.filter(owner=owner).select_related("service")

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(email__icontains=q)
            | Q(customer_name__icontains=q)
            | Q(acquisition_method__icontains=q)
        )

    status = (request.GET.get("estado") or "").strip()
    if status in {StockEmail.Status.AVAILABLE, StockEmail.Status.SOLD}:
        qs = qs.filter(status=status)
    else:
        status = ""

    service_id = (request.GET.get("servicio") or "").strip()
    if service_id.isdigit():
        qs = qs.filter(service_id=int(service_id))
    else:
        service_id = ""

    method = (request.GET.get("metodo") or "").strip()
    if method:
        qs = qs.filter(acquisition_method__iexact=method)

    emails = list(
        qs.order_by("service__name", "status", "inventory_number", "email")
    )


    # Resumen por servicio (disponibles / vendidos), sobre TODO el stock.
    services = list(Service.objects.filter(owner=owner).order_by("name"))
    all_stock = StockEmail.objects.filter(owner=owner)
    counts: dict[int, dict] = {}
    for row in all_stock.values("service_id", "status"):
        c = counts.setdefault(row["service_id"], {"available": 0, "sold": 0})
        c[row["status"]] = c.get(row["status"], 0) + 1
    summary = []
    for svc in services:
        c = counts.get(svc.pk, {"available": 0, "sold": 0})
        summary.append({
            "service": svc,
            "available": c.get("available", 0),
            "sold": c.get("sold", 0),
            "total": c.get("available", 0) + c.get("sold", 0),
        })

    total_available = sum(s["available"] for s in summary)
    total_sold = sum(s["sold"] for s in summary)
    acquisition_methods = list(
        all_stock.exclude(acquisition_method="")
        .order_by("acquisition_method")
        .values_list("acquisition_method", flat=True)
        .distinct()
    )

    ctx = _ctx(
        request, tenant,
        title="Correos", jc_active="emails",
        emails=emails, services=services, summary=summary,
        q=q, status=status, service_id=service_id, method=method,
        acquisition_methods=acquisition_methods,
        total_available=total_available, total_sold=total_sold,
    )
    return render(request, "jheliztv/emails.html", ctx)


@tenant_required
@require_POST
def stock_email_add(request, tenant):
    owner = request.user
    service = get_object_or_404(
        Service, pk=request.POST.get("service") or 0, owner=owner
    )
    emails = _split_emails(request.POST.get("emails") or "")
    if not emails:
        messages.error(request, "Ingresá al menos un correo.")
        return redirect("jheliztv_emails")
    password = (request.POST.get("password") or "").strip()
    acquisition_method = (request.POST.get("acquisition_method") or "").strip()
    customer_name = (request.POST.get("customer_name") or "").strip()
    status = (
        StockEmail.Status.SOLD
        if request.POST.get("status") == StockEmail.Status.SOLD
        else StockEmail.Status.AVAILABLE
    )
    if status == StockEmail.Status.SOLD and not customer_name:
        messages.error(request, "Indicá el cliente para agregar correos vendidos.")
        return redirect("jheliztv_emails")
    created = skipped = 0
    for email in emails:
        obj, was_created = StockEmail.objects.get_or_create(
            owner=owner, service=service, email=email.strip().lower(),
            defaults={
                "password": password,
                "acquisition_method": acquisition_method,
                "customer_name": customer_name,
                "status": status,
            },
        )
        if was_created:
            created += 1
        else:
            skipped += 1
    if created:
        messages.success(
            request,
            f"Se agregaron {created} correo{'s' if created != 1 else ''} a {service.name}.",
        )
    if skipped:
        messages.info(request, f"{skipped} ya estaban cargados y se omitieron.")
    return redirect("jheliztv_emails")


@tenant_required
@require_POST
def stock_email_toggle(request, tenant, pk):
    item = get_object_or_404(StockEmail, pk=pk, owner=request.user)
    if item.is_available:
        customer_name = (request.POST.get("customer_name") or "").strip()
        if not customer_name:
            messages.error(request, "Indicá el cliente antes de marcar el correo como vendido.")
            return redirect("jheliztv_emails")
        item.status = StockEmail.Status.SOLD
        item.customer_name = customer_name
    else:
        item.status = StockEmail.Status.AVAILABLE
        item.customer_name = ""
    item.save(update_fields=["status", "customer_name", "updated_at"])
    messages.success(
        request,
        f"{item.email} marcado como {item.get_status_display().lower()}.",
    )
    nxt = request.POST.get("next") or ""
    if nxt.startswith("/") and not nxt.startswith("//"):
        return redirect(nxt)
    return redirect("jheliztv_emails")


@tenant_required
@require_POST
def stock_email_edit(request, tenant, pk):
    item = get_object_or_404(StockEmail, pk=pk, owner=request.user)
    email = (request.POST.get("email") or "").strip().lower()
    if not email:
        messages.error(request, "El correo no puede quedar vacío.")
        return redirect("jheliztv_emails")
    clash = (
        StockEmail.objects.filter(
            owner=request.user, service=item.service, email=email
        )
        .exclude(pk=item.pk)
        .exists()
    )
    if clash:
        messages.error(request, "Ese correo ya está cargado en este servicio.")
        return redirect("jheliztv_emails")
    item.email = email
    item.password = (request.POST.get("password") or "").strip()
    item.acquisition_method = (request.POST.get("acquisition_method") or "").strip()
    item.customer_name = (request.POST.get("customer_name") or "").strip()
    if request.POST.get("status") in {StockEmail.Status.AVAILABLE, StockEmail.Status.SOLD}:
        item.status = request.POST["status"]
    if item.status == StockEmail.Status.SOLD and not item.customer_name:
        messages.error(request, "Indicá el cliente para guardar el correo como vendido.")
        return redirect("jheliztv_emails")
    item.save()
    messages.success(request, "Correo actualizado.")
    return redirect("jheliztv_emails")


@tenant_required
@require_POST
def stock_email_delete(request, tenant, pk):
    get_object_or_404(StockEmail, pk=pk, owner=request.user).delete()
    messages.success(request, "Correo eliminado del stock.")
    return redirect("jheliztv_emails")


@tenant_required
@require_GET
def stock_email_secret(request, tenant, pk):
    """Entrega la clave únicamente al propietario autenticado."""
    item = get_object_or_404(StockEmail, pk=pk, owner=request.user)
    response = JsonResponse({"password": item.password or ""})
    response["Cache-Control"] = "no-store, private"
    response["Pragma"] = "no-cache"
    return response


# ---------------------------------------------------------------------------
# Movimientos + buscador + notificaciones
# ---------------------------------------------------------------------------
@tenant_required
@require_POST
def transaction_add(request, tenant):
    form = TransactionForm(request.POST)
    form.fields["client"].queryset = Client.objects.filter(owner=request.user)
    if form.is_valid():
        tx = form.save(commit=False)
        tx.owner = request.user
        control = ControlSettings.load(request.user)
        if tx.currency != normalize_currency(control.currency) and not request.POST.get("exchange_rate"):
            messages.error(request, f"Ingresa el tipo de cambio de {tx.currency} a {control.currency}.")
            return redirect("jheliztv_dashboard")
        tx.set_conversion(control.currency, form.cleaned_data.get("exchange_rate"))
        tx.save()
        messages.success(request, "Movimiento registrado.")
    else:
        messages.error(request, "Revisá el movimiento.")
    return redirect("jheliztv_dashboard")


@tenant_required
def money_settings(request, tenant):
    control = ControlSettings.load(request.user)
    if request.method == "POST":
        form = ControlSettingsForm(request.POST, instance=control)
        if form.is_valid():
            form.save()
            messages.success(request, "País y moneda principal actualizados.")
            return redirect("jheliztv_money_settings")
    else:
        form = ControlSettingsForm(instance=control)
    return render(request, "jheliztv/money_settings.html", _ctx(
        request, tenant, title="Monedas", jc_active="money", form=form,
    ))


@tenant_required
def support_inbox(request, tenant):
    status = (request.GET.get("estado") or "active").strip()
    qs = SupportTicket.objects.filter(owner=request.user).select_related(
        "client", "subscription__service"
    ).prefetch_related("messages")
    if status == "active":
        qs = qs.exclude(status=SupportTicket.Status.RESOLVED)
    elif status in SupportTicket.Status.values:
        qs = qs.filter(status=status)
    tickets = list(qs[:100])
    selected = None
    selected_id = (request.GET.get("ticket") or "").strip()
    if selected_id.isdigit():
        selected = next((item for item in tickets if item.pk == int(selected_id)), None)
        if selected is None:
            selected = SupportTicket.objects.filter(
                pk=selected_id, owner=request.user
            ).select_related("client", "subscription__service").prefetch_related("messages").first()
    if selected is None and tickets:
        selected = tickets[0]
    counts = {
        key: SupportTicket.objects.filter(owner=request.user, status=key).count()
        for key in SupportTicket.Status.values
    }
    contacts = []
    bot_username = settings.JHELIZ_CONTROL_TELEGRAM_BOT_USERNAME.lstrip("@")
    for client in Client.objects.filter(owner=request.user).order_by("name"):
        contact, _ = SupportContact.objects.get_or_create(owner=request.user, client=client)
        contacts.append({
            "client": client,
            "link": f"https://t.me/{bot_username}?start=support_{contact.token.hex}",
            "linked": bool(contact.telegram_chat_id),
        })
    return render(request, "jheliztv/support.html", _ctx(
        request, tenant, title="Soporte", jc_active="support",
        tickets=tickets, selected=selected, counts=counts, status=status,
        support_contacts=contacts, mobile_ticket_open=selected_id.isdigit(),
    ))


@tenant_required
@require_POST
def support_reply(request, tenant, pk):
    ticket = get_object_or_404(SupportTicket, pk=pk, owner=request.user)
    text = (request.POST.get("message") or "").strip()
    if not text:
        messages.error(request, "Escribe una respuesta antes de enviarla.")
        return redirect(f"{reverse('jheliztv_support')}?ticket={ticket.pk}")
    add_support_message(ticket, SupportMessage.Sender.AGENT, text)
    if ticket.customer_chat_id:
        from .telegram_alerts import _button, _markup, send_message
        send_message(
            ticket.customer_chat_id,
            f"💬 <b>Respuesta a {ticket.display_number}</b>\n\n{html.escape(text)}",
            _markup([[_button("✍️ Responder", f"cs_reply:{ticket.pk}"), _button("✅ Solucionado", f"cs_close:{ticket.pk}")]]),
        )
        messages.success(request, "Respuesta enviada al cliente.")
    else:
        messages.warning(request, "Respuesta guardada. El cliente todavía no vinculó Telegram.")
    return redirect(f"{reverse('jheliztv_support')}?ticket={ticket.pk}")


@tenant_required
@require_POST
def support_status(request, tenant, pk):
    ticket = get_object_or_404(SupportTicket, pk=pk, owner=request.user)
    status = request.POST.get("status")
    if not set_support_status(ticket, status):
        messages.error(request, "Estado no válido.")
    else:
        messages.success(request, "Estado del ticket actualizado.")
        if status == SupportTicket.Status.RESOLVED and ticket.customer_chat_id:
            from .telegram_alerts import send_message
            send_message(ticket.customer_chat_id, f"✅ Tu ticket <b>{ticket.display_number}</b> fue marcado como resuelto.")
    return redirect(f"{reverse('jheliztv_support')}?ticket={ticket.pk}")


@tenant_required
def renewals_inbox(request, tenant):
    renewals = RenewalRequest.objects.filter(owner=request.user).select_related(
        "subscription__client", "subscription__service", "payment_method"
    )[:150]
    methods = ResellerPaymentMethod.objects.filter(owner=request.user)
    return render(request, "jheliztv/renewals.html", _ctx(
        request, tenant, title="Renovaciones", jc_active="renewals",
        renewals=renewals, payment_methods=methods,
    ))


@tenant_required
@require_POST
def payment_method_add(request, tenant):
    label = (request.POST.get("label") or "").strip()
    details = (request.POST.get("details") or "").strip()
    kind = request.POST.get("kind")
    if not label or not details or kind not in ResellerPaymentMethod.Kind.values:
        messages.error(request, "Completa el nombre y los datos del método de pago.")
        return redirect("jheliztv_renewals")
    ResellerPaymentMethod.objects.create(
        owner=request.user, kind=kind, label=label,
        holder=(request.POST.get("holder") or "").strip(),
        details=details, qr_image=request.FILES.get("qr_image"),
    )
    messages.success(request, "Método de pago agregado.")
    return redirect("jheliztv_renewals")


@tenant_required
@require_POST
def payment_method_delete(request, tenant, pk):
    get_object_or_404(ResellerPaymentMethod, pk=pk, owner=request.user).delete()
    messages.success(request, "Método de pago eliminado.")
    return redirect("jheliztv_renewals")


@tenant_required
@require_POST
def renewal_review(request, tenant, pk):
    renewal = get_object_or_404(RenewalRequest, pk=pk, owner=request.user)
    action = request.POST.get("action")
    if action == "approve":
        try:
            days = max(1, min(3660, int(request.POST.get("days") or 30)))
        except ValueError:
            days = 30
        sub, error = renew_subscription_operation(request.user, renewal.subscription_id, days)
        if error:
            messages.error(request, "No se pudo renovar la suscripción.")
        else:
            renewal.status = RenewalRequest.Status.APPROVED
            renewal.reviewed_at = timezone.now()
            renewal.save(update_fields=["status", "reviewed_at", "updated_at"])
            messages.success(request, f"Pago aprobado y suscripción renovada por {days} días.")
    elif action == "reject":
        renewal.status = RenewalRequest.Status.REJECTED
        renewal.rejection_reason = (request.POST.get("reason") or "El comprobante no pudo verificarse.")[:500]
        renewal.reviewed_at = timezone.now()
        renewal.save(update_fields=["status", "rejection_reason", "reviewed_at", "updated_at"])
        messages.success(request, "Comprobante rechazado.")
    return redirect("jheliztv_renewals")


@tenant_required
def renewal_proof(request, tenant, pk):
    renewal = get_object_or_404(RenewalRequest, pk=pk, owner=request.user)
    if not renewal.proof:
        return HttpResponse(status=404)
    response = FileResponse(renewal.proof.open("rb"), content_type="application/octet-stream")
    response["Content-Disposition"] = f'inline; filename="comprobante-{renewal.display_number}.jpg"'
    response["Cache-Control"] = "no-store, private"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@tenant_required
def search(request, tenant):
    owner = request.user
    q = (request.GET.get("q") or "").strip()
    clients_found, subs_found = [], []
    if q:
        clients_found = list(
            Client.objects.filter(owner=owner).filter(
                Q(name__icontains=q) | Q(telegram__icontains=q)
                | Q(email__icontains=q) | Q(whatsapp__icontains=q)
            )[:50]
        )
        subs_found = _decorate_subs(list(
            Subscription.objects.filter(owner=owner, is_archived=False)
            .filter(
                Q(account_email__icontains=q) | Q(client__name__icontains=q)
                | Q(client__telegram__icontains=q) | Q(service__name__icontains=q)
            )
            .select_related("client", "service")[:50]
        ))
    ctx = _ctx(
        request, tenant,
        title=f"Buscar: {q}" if q else "Buscar",
        q=q, clients_found=clients_found, subs_found=subs_found,
    )
    return render(request, "jheliztv/search.html", ctx)


@tenant_required
def notifications_json(request, tenant):
    alerts = _expiry_alerts(request.user)
    data = [{
        "id": s.id,
        "service": s.service.name,
        "client": s.client.name,
        "status": s.status_color,
        "time_left": s.time_left_label,
        "url": reverse("jheliztv_service_detail", args=[s.service_id]),
    } for s in alerts]
    return JsonResponse({"count": len(data), "alerts": data})


@tenant_required
def telegram_settings(request, tenant):
    connection, _ = TelegramConnection.objects.get_or_create(owner=request.user)
    link_url = ""
    if request.method == "POST":
        selected = [
            value for value in (7, 3, 1, 0)
            if request.POST.get(f"window_{value}") == "on"
        ]
        connection.notify_windows = selected or [7, 3, 1, 0]
        raw_token = secrets.token_urlsafe(32)
        connection.link_token_digest = hashlib.sha256(raw_token.encode()).hexdigest()
        connection.link_expires_at = timezone.now() + timedelta(minutes=15)
        connection.save()
        username = settings.JHELIZ_CONTROL_TELEGRAM_BOT_USERNAME
        link_url = f"https://t.me/{username}?start={raw_token}"
    return render(
        request,
        "jheliztv/telegram.html",
        _ctx(
            request,
            tenant,
            connection=connection,
            link_url=link_url,
            telegram_bot_username=settings.JHELIZ_CONTROL_TELEGRAM_BOT_USERNAME,
            jc_active="telegram",
        ),
    )


@tenant_required
@require_POST
def telegram_unlink(request, tenant):
    TelegramConnection.objects.filter(owner=request.user).update(
        chat_id=None,
        telegram_username="",
        link_token_digest="",
        link_expires_at=None,
        is_enabled=False,
        last_digest_date=None,
    )
    messages.success(request, "Telegram fue desvinculado.")
    return redirect("jheliztv_telegram")


@tenant_required
def whatsapp_settings(request, tenant):
    connection, _ = WhatsAppConnection.objects.get_or_create(owner=request.user)
    if request.method == "POST":
        connection.reminder_days = [
            day for day in (7, 3, 1, 0)
            if request.POST.get(f"window_{day}") == "on"
        ] or [1]
        connection.template_name = (
            request.POST.get("template_name", "").strip()
            or "recordatorio_vencimiento"
        )[:128]
        connection.template_language = (
            request.POST.get("template_language", "").strip() or "es"
        )[:16]
        connection.is_enabled = request.POST.get("is_enabled") == "on"
        connection.save()
        messages.success(request, "Configuracion de WhatsApp guardada.")
        return redirect("jheliztv_whatsapp")
    return render(request, "jheliztv/whatsapp.html", _ctx(
        request, tenant,
        connection=connection,
        meta_ready=all([
            settings.META_APP_ID, settings.META_APP_SECRET, settings.META_CONFIG_ID,
        ]),
        meta_app_id=settings.META_APP_ID,
        meta_config_id=settings.META_CONFIG_ID,
        whatsapp_windows=[
            (7, "7 dias antes"), (3, "3 dias antes"),
            (1, "1 dia antes"), (0, "El mismo dia"),
        ],
        jc_active="whatsapp",
    ))


@tenant_required
@require_POST
def whatsapp_signup_complete(request, tenant):
    try:
        payload = json.loads(request.body)
        required = ("code", "waba_id", "phone_number_id")
        if any(not payload.get(key) for key in required):
            return JsonResponse({"ok": False, "error": "Datos incompletos de Meta."}, status=400)
        connection = finish_signup(request.user, **{key: payload[key] for key in required})
        return JsonResponse({
            "ok": True,
            "phone": connection.display_phone_number,
            "name": connection.verified_name,
        })
    except (ValueError, MetaAPIError) as exc:
        WhatsAppConnection.objects.update_or_create(
            owner=request.user,
            defaults={"status": WhatsAppConnection.Status.ERROR, "last_error": str(exc)[:1000]},
        )
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)


@tenant_required
@require_POST
def whatsapp_unlink(request, tenant):
    WhatsAppConnection.objects.filter(owner=request.user).update(
        access_token="", waba_id="", phone_number_id=None,
        display_phone_number="", verified_name="",
        status=WhatsAppConnection.Status.DISCONNECTED,
        is_enabled=False, last_error="",
    )
    messages.success(request, "WhatsApp Business fue desvinculado.")
    return redirect("jheliztv_whatsapp")


@csrf_exempt
def whatsapp_webhook(request):
    if request.method == "GET":
        if (
            request.GET.get("hub.mode") == "subscribe"
            and request.GET.get("hub.verify_token") == settings.META_WEBHOOK_VERIFY_TOKEN
        ):
            return HttpResponse(request.GET.get("hub.challenge", ""))
        return HttpResponse("Verificacion rechazada", status=403)
    if request.method != "POST":
        return HttpResponse(status=405)
    if not verify_signature(request.body, request.headers.get("X-Hub-Signature-256", "")):
        return HttpResponse("Firma invalida", status=403)
    try:
        process_webhook(json.loads(request.body))
    except (ValueError, TypeError):
        return HttpResponse("JSON invalido", status=400)
    return HttpResponse("EVENT_RECEIVED")
