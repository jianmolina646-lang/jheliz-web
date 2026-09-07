"""Vistas de **Jheliz Control** (módulo de gestión para revendedor).

Montadas bajo `/panel-jheliz-2026/jheliz-control/` ANTES del catch-all
`admin.site.urls`. Todas requieren staff.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from urllib.parse import quote

from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ClientForm, ServiceForm, SubscriptionForm, TransactionForm
from .models import (
    Client,
    ControlSettings,
    Service,
    ServiceCategory,
    Subscription,
    Transaction,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ctx(request, **extra):
    owner = request.user
    settings_obj = ControlSettings.load(owner)
    base = {
        **admin.site.each_context(request),
        "jc_settings": settings_obj,
        "jc_currency": settings_obj.currency,
        "jc_alerts": _expiry_alerts(owner),
        **extra,
    }
    return base


def _expiry_alerts(owner, within_days: int = 3):
    """Suscripciones por vencer (≤ within_days) o ya vencidas, para la campana."""
    now = timezone.now()
    soon = now + timedelta(days=within_days)
    qs = (
        Subscription.objects.filter(owner=owner, is_archived=False, expires_at__lte=soon)
        .select_related("client", "service")
        .order_by("expires_at")
    )
    return list(qs)


def _predefined_message(sub: Subscription) -> str:
    """Texto automático con datos de la cuenta + vencimiento (WhatsApp/Telegram)."""
    vence = timezone.localtime(sub.expires_at).strftime("%d/%m/%Y %H:%M")
    lines = [
        f"¡Hola {sub.client.name}! 👋",
        f"Tu suscripción de *{sub.service.name}* está activa.",
        f"📧 Cuenta: {sub.account_email}",
    ]
    if sub.account_password:
        lines.append(f"🔑 Clave: {sub.account_password}")
    if sub.plan == Subscription.Plan.PERFIL and sub.profile_name:
        lines.append(f"👤 Perfil: {sub.profile_name}"
                     + (f" · PIN: {sub.profile_pin}" if sub.profile_pin else ""))
    lines.append(f"⏳ Vence: {vence}")
    lines.append("Cualquier cosa me escribís. ¡Gracias! 🐱")
    return "\n".join(lines)


def _decorate_subs(subs):
    """Adjunta links de mensajería a cada suscripción para el template."""
    out = []
    for s in subs:
        msg = _predefined_message(s)
        s.wa_link = (
            f"https://wa.me/{s.client.whatsapp_digits}?text={quote(msg)}"
            if s.client.whatsapp_digits else ""
        )
        s.tg_link = (
            f"https://t.me/{s.client.telegram_handle}" if s.client.telegram_handle else ""
        )
        out.append(s)
    return out


# ---------------------------------------------------------------------------
# Dashboard (Inicio)
# ---------------------------------------------------------------------------
@staff_member_required
def dashboard(request):
    now = timezone.now()

    owner = request.user
    # Métricas rápidas
    total_clients = Client.objects.filter(owner=owner).count()
    settings_obj = ControlSettings.load(owner)

    # Serie ingresos vs egresos por mes (últimos 6 meses).
    series = []
    months = []
    y, mo = now.year, now.month
    for _ in range(6):
        months.append((y, mo))
        mo -= 1
        if mo == 0:
            mo = 12
            y -= 1
    months.reverse()

    max_val = Decimal("1")
    for (yy, mm) in months:
        income = (
            Transaction.objects.filter(
                owner=owner, kind=Transaction.Kind.INCOME, occurred_at__year=yy, occurred_at__month=mm
            ).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        )
        expense = (
            Transaction.objects.filter(
                owner=owner, kind=Transaction.Kind.EXPENSE, occurred_at__year=yy, occurred_at__month=mm
            ).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        )
        max_val = max(max_val, income, expense)
        label = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep",
                 "Oct", "Nov", "Dic"][mm - 1]
        series.append({"label": label, "income": income, "expense": expense})

    # alturas en % para las barras
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
        request,
        title="Jheliz Control",
        jc_active="dashboard",
        total_clients=total_clients,
        active_subs=active_subs,
        series=series,
        max_val=max_val,
        total_income=total_income,
        total_expense=total_expense,
        net=total_income - total_expense,
    )
    return render(request, "gestion/dashboard.html", ctx)


# ---------------------------------------------------------------------------
# Tablero de Servicios
# ---------------------------------------------------------------------------
@staff_member_required
def services_board(request):
    owner = request.user
    categories = ServiceCategory.objects.prefetch_related("services").all()
    # servicios sin categoría
    uncategorized = Service.objects.filter(owner=owner, category__isnull=True)
    cats = []
    for c in categories:
        svcs = list(c.services.filter(owner=owner))
        cats.append({"cat": c, "services": svcs})
    ctx = _ctx(
        request,
        title="Tablero de servicios",
        jc_active="services",
        categories=cats,
        uncategorized=list(uncategorized),
        form=ServiceForm(),
        all_categories=ServiceCategory.objects.all(),
    )
    return render(request, "gestion/services.html", ctx)


@staff_member_required
@require_POST
def service_add(request):
    form = ServiceForm(request.POST, request.FILES)
    if form.is_valid():
        svc = form.save(commit=False)
        svc.owner = request.user
        svc.save()
        messages.success(request, "Servicio agregado.")
    else:
        messages.error(request, "Revisá los datos del servicio.")
    return redirect("gestion_services")


@staff_member_required
@require_POST
def service_delete(request, pk):
    svc = get_object_or_404(Service, pk=pk, owner=request.user)
    svc.delete()
    messages.success(request, "Servicio eliminado.")
    return redirect("gestion_services")


@staff_member_required
def service_detail(request, pk):
    owner = request.user
    service = get_object_or_404(Service, pk=pk, owner=owner)
    subs = _decorate_subs(
        list(service.subscriptions.filter(owner=request.user, client__owner=request.user, is_archived=False).select_related("client"))
    )
    form = SubscriptionForm(initial={"service": service})
    form.fields["client"].queryset = Client.objects.filter(owner=owner)
    ctx = _ctx(
        request,
        title=service.name,
        jc_active="services",
        service=service,
        subs=subs,
        form=form,
        clients=Client.objects.filter(owner=owner),
    )
    return render(request, "gestion/service_detail.html", ctx)


# ---------------------------------------------------------------------------
# Suscripciones (CRUD + renovar)
# ---------------------------------------------------------------------------
@staff_member_required
@require_POST
def subscription_add(request):
    owner = request.user
    form = SubscriptionForm(request.POST)
    form.fields["client"].queryset = Client.objects.filter(owner=owner)
    form.fields["service"].queryset = Service.objects.filter(owner=owner)
    if form.is_valid():
        sub = form.save(commit=False)
        sub.owner = owner
        sub.save()
        # Registramos el ingreso automático si hay costo.
        if sub.cost and sub.cost > 0:
            Transaction.objects.create(
                owner=owner,
                kind=Transaction.Kind.INCOME,
                amount=sub.cost,
                currency=sub.currency,
                description=f"Venta {sub.service.name} · {sub.client.name}",
                client=sub.client,
                subscription=sub,
            )
        if sub.investment and sub.investment > 0:
            Transaction.objects.create(
                owner=owner,
                kind=Transaction.Kind.EXPENSE,
                amount=sub.investment,
                currency=sub.currency,
                description=f"Inversión {sub.service.name}",
                client=sub.client,
                subscription=sub,
            )
        messages.success(request, "Suscripción creada.")
        return redirect("gestion_service_detail", pk=sub.service_id)
    messages.error(request, "Revisá los datos de la suscripción.")
    service_id = request.POST.get("service")
    if service_id:
        return redirect("gestion_service_detail", pk=service_id)
    return redirect("gestion_dashboard")


@staff_member_required
@require_POST
def subscription_edit(request, pk):
    sub = get_object_or_404(Subscription, pk=pk, owner=request.user)
    form = SubscriptionForm(request.POST, instance=sub)
    form.fields["client"].queryset = Client.objects.filter(owner=request.user)
    form.fields["service"].queryset = Service.objects.filter(owner=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, "Suscripción actualizada.")
    else:
        messages.error(request, "No se pudo actualizar la suscripción.")
    return redirect("gestion_service_detail", pk=sub.service_id)


@staff_member_required
@require_POST
def subscription_renew(request, pk):
    sub = get_object_or_404(Subscription, pk=pk, owner=request.user)
    try:
        days = int(request.POST.get("days", 30))
    except (TypeError, ValueError):
        days = 30
    sub.renew(days)
    messages.success(request, f"Renovada +{days} días. Nuevo vencimiento: "
                              f"{timezone.localtime(sub.expires_at):%d/%m/%Y}.")
    return redirect("gestion_service_detail", pk=sub.service_id)


@staff_member_required
@require_POST
def subscription_delete(request, pk):
    sub = get_object_or_404(Subscription, pk=pk, owner=request.user)
    service_id = sub.service_id
    sub.delete()
    messages.success(request, "Suscripción eliminada.")
    return redirect("gestion_service_detail", pk=service_id)


# ---------------------------------------------------------------------------
# Mis Clientes
# ---------------------------------------------------------------------------
@staff_member_required
def clients(request):
    qs = Client.objects.filter(owner=request.user).prefetch_related("subscriptions__service")
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(telegram__icontains=q)
            | Q(email__icontains=q) | Q(whatsapp__icontains=q)
            | Q(subscriptions__account_email__icontains=q)
        ).distinct()
    ctx = _ctx(
        request,
        title="Mis clientes",
        jc_active="clients",
        clients=list(qs),
        form=ClientForm(),
        q=q,
    )
    return render(request, "gestion/clients.html", ctx)


@staff_member_required
@require_POST
def client_add(request):
    form = ClientForm(request.POST)
    if form.is_valid():
        client = form.save(commit=False)
        client.owner = request.user
        client.save()
        messages.success(request, "Cliente agregado.")
    else:
        messages.error(request, "Revisá los datos del cliente.")
    return redirect("gestion_clients")


@staff_member_required
@require_POST
def client_edit(request, pk):
    client = get_object_or_404(Client, pk=pk, owner=request.user)
    form = ClientForm(request.POST, instance=client)
    if form.is_valid():
        form.save()
        messages.success(request, "Cliente actualizado.")
    else:
        messages.error(request, "No se pudo actualizar el cliente.")
    return redirect("gestion_clients")


@staff_member_required
@require_POST
def client_delete(request, pk):
    client = get_object_or_404(Client, pk=pk, owner=request.user)
    client.delete()
    messages.success(request, "Cliente eliminado.")
    return redirect("gestion_clients")


@staff_member_required
def client_report_pdf(request, pk):
    """Genera un PDF con todos los servicios del cliente (correos + vencimientos)."""
    client = get_object_or_404(Client, pk=pk, owner=request.user)
    subs = list(client.subscriptions.filter(owner=request.user, service__owner=request.user, is_archived=False).select_related("service"))

    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    green = colors.HexColor("#10b981")
    dark = colors.HexColor("#1f2937")

    # Header
    c.setFillColor(green)
    c.rect(0, height - 30 * mm, width, 30 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(20 * mm, height - 18 * mm, "Jheliz Control")
    c.setFont("Helvetica", 11)
    c.drawString(20 * mm, height - 25 * mm, "Reporte de servicios del cliente")

    # Cliente
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

    # Tabla header
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
# Movimientos (libro de caja)
# ---------------------------------------------------------------------------
@staff_member_required
@require_POST
def transaction_add(request):
    form = TransactionForm(request.POST)
    form.fields["client"].queryset = Client.objects.filter(owner=request.user)
    if form.is_valid():
        tx = form.save(commit=False)
        tx.owner = request.user
        tx.save()
        messages.success(request, "Movimiento registrado.")
    else:
        messages.error(request, "Revisá el movimiento.")
    return redirect("gestion_dashboard")


# ---------------------------------------------------------------------------
# Buscador global + notificaciones
# ---------------------------------------------------------------------------
@staff_member_required
def search(request):
    owner = request.user
    q = (request.GET.get("q") or "").strip()
    clients_found = []
    subs_found = []
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
        request,
        title=f"Buscar: {q}" if q else "Buscar",
        q=q,
        clients_found=clients_found,
        subs_found=subs_found,
    )
    return render(request, "gestion/search.html", ctx)


@staff_member_required
def notifications_json(request):
    alerts = _expiry_alerts(request.user)
    data = []
    for s in alerts:
        data.append({
            "id": s.id,
            "service": s.service.name,
            "client": s.client.name,
            "status": s.status_color,
            "time_left": s.time_left_label,
            "url": reverse("gestion_service_detail", args=[s.service_id]),
        })
    return JsonResponse({"count": len(data), "alerts": data})
