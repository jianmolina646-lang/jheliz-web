"""Web del **inquilino** de Jheliz Control (producto SaaS en jheliztv.xyz).

A diferencia de ``views.py`` (que vive dentro del panel admin y usa
``@staff_member_required``), estas vistas son la cara pública del producto que
se **alquila**: cada inquilino entra con su propio usuario/contraseña y ve solo
sus datos. El cobro del alquiler es por **Yape con aprobación manual**.

Reutiliza el mismo diseño "Jheliz Control" (clases ``jc-*``) mediante templates
standalone bajo ``templates/jheliztv/`` (no dependen del admin).
"""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import get_user_model
from django.db.models import Prefetch, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ClientForm, ServiceForm, SubscriptionForm, TransactionForm
from .models import (
    Client,
    ControlSettings,
    SaasSettings,
    Service,
    ServiceCategory,
    Subscription,
    Tenant,
    TenantPayment,
    Transaction,
)
from .views import _decorate_subs  # reuso de helpers

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
            ).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        )
        expense = (
            Transaction.objects.filter(
                owner=owner, kind=Transaction.Kind.EXPENSE,
                occurred_at__year=yy, occurred_at__month=mm,
            ).aggregate(s=Sum("amount"))["s"] or Decimal("0")
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
        .aggregate(s=Sum("amount"))["s"] or Decimal("0")
    )
    total_expense = (
        Transaction.objects.filter(owner=owner, kind=Transaction.Kind.EXPENSE)
        .aggregate(s=Sum("amount"))["s"] or Decimal("0")
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
    form = SubscriptionForm(initial={"service": service})
    form.fields["client"].queryset = Client.objects.filter(owner=owner)
    ctx = _ctx(
        request, tenant,
        title=service.name, jc_active="services",
        service=service, subs=subs, form=form,
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
        expires = starts + timedelta(days=days)
    currency = ControlSettings.load(owner).currency or "S/"

    # Los totales ("¿cuánto vendiste/invertiste en total?") se reparten en
    # partes iguales entre los correos cargados.
    n = len(emails)
    cost_each = (_dec(post.get("cost")) / n).quantize(Decimal("0.01"))
    inv_each = (_dec(post.get("investment")) / n).quantize(Decimal("0.01"))

    for email in emails:
        sub = Subscription.objects.create(
            owner=owner, client=client, service=service,
            account_email=email, account_password=password,
            plan=plan, profiles=profiles,
            profile_name=profile_name, profile_pin=profile_pin,
            plan_label=plan_label, currency=currency,
            cost=cost_each, investment=inv_each,
            starts_at=starts, expires_at=expires,
        )
        if cost_each > 0:
            Transaction.objects.create(
                owner=owner, kind=Transaction.Kind.INCOME, amount=cost_each,
                currency=currency,
                description=f"Venta {service.name} · {client.name}",
                client=client, subscription=sub,
            )
        if inv_each > 0:
            Transaction.objects.create(
                owner=owner, kind=Transaction.Kind.EXPENSE, amount=inv_each,
                currency=currency,
                description=f"Inversión {service.name}",
                client=client, subscription=sub,
            )

    if n == 1:
        messages.success(request, "Suscripción creada.")
    else:
        messages.success(request, f"Se crearon {n} suscripciones.")
    return redirect("jheliztv_service_detail", pk=service.pk)


@tenant_required
@require_POST
def subscription_edit(request, tenant, pk):
    sub = get_object_or_404(Subscription, pk=pk, owner=request.user)
    form = SubscriptionForm(request.POST, instance=sub)
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
    sub.renew(days)
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

    ctx = _ctx(
        request, tenant,
        title="Mis clientes", jc_active="clients",
        clients=clients, form=ClientForm(), q=q, sort=sort,
    )
    return render(request, "jheliztv/clients.html", ctx)


@tenant_required
@require_POST
def client_add(request, tenant):
    form = ClientForm(request.POST)
    if form.is_valid():
        client = form.save(commit=False)
        client.owner = request.user
        client.save()
        messages.success(request, "Cliente agregado.")
    else:
        messages.error(request, "Revisá los datos del cliente.")
    return redirect("jheliztv_clients")


@tenant_required
@require_POST
def client_edit(request, tenant, pk):
    client = get_object_or_404(Client, pk=pk, owner=request.user)
    form = ClientForm(request.POST, instance=client)
    if form.is_valid():
        form.save()
        messages.success(request, "Cliente actualizado.")
    else:
        messages.error(request, "No se pudo actualizar el cliente.")
    return redirect("jheliztv_clients")


@tenant_required
@require_POST
def client_delete(request, tenant, pk):
    get_object_or_404(Client, pk=pk, owner=request.user).delete()
    messages.success(request, "Cliente eliminado.")
    return redirect("jheliztv_clients")


@tenant_required
def client_report_pdf(request, tenant, pk):
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    client = get_object_or_404(Client, pk=pk, owner=request.user)
    subs = list(client.subscriptions.filter(is_archived=False).select_related("service"))

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
    c.drawString(70 * mm, y, "Cuenta / correo")
    c.drawString(140 * mm, y, "Plan")
    c.drawString(165 * mm, y, "Vence")
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
        c.drawString(22 * mm, y, s.service.name[:28])
        c.drawString(70 * mm, y, s.account_email[:34])
        c.drawString(140 * mm, y, s.get_plan_display()[:12])
        c.drawString(165 * mm, y, timezone.localtime(s.expires_at).strftime("%d/%m/%Y"))
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
        tx.save()
        messages.success(request, "Movimiento registrado.")
    else:
        messages.error(request, "Revisá el movimiento.")
    return redirect("jheliztv_dashboard")


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
