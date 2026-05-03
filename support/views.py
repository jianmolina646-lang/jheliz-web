from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import CodeRequestForm, TicketCreateForm, TicketReplyForm
from .models import CodeRequest, Ticket, TicketMessage


@login_required
def ticket_list(request):
    tickets = request.user.tickets.all()
    return render(request, "support/ticket_list.html", {"tickets": tickets})


@login_required
def ticket_create(request):
    initial = {}
    order_uuid = request.GET.get("pedido")
    if order_uuid:
        initial["order"] = request.user.orders.filter(uuid=order_uuid).first()
    if request.method == "POST":
        form = TicketCreateForm(request.POST, user=request.user)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.user = request.user
            ticket.status = Ticket.Status.PENDING_ADMIN
            ticket.save()
            TicketMessage.objects.create(
                ticket=ticket,
                author=request.user,
                body=form.cleaned_data["body"],
                is_from_staff=False,
            )
            messages.success(request, f"Ticket #{ticket.id} creado. Te respondemos muy pronto.")
            return redirect("support:detail", pk=ticket.id)
    else:
        form = TicketCreateForm(user=request.user, initial=initial)
    return render(request, "support/ticket_form.html", {"form": form})


def _user_can_view(ticket: Ticket, user) -> bool:
    return ticket.user_id == user.id or user.is_staff


@login_required
def ticket_detail(request, pk: int):
    ticket = get_object_or_404(Ticket, pk=pk)
    if not _user_can_view(ticket, request.user):
        raise Http404
    reply_form = TicketReplyForm()
    return render(
        request,
        "support/ticket_detail.html",
        {
            "ticket": ticket,
            "reply_form": reply_form,
            "messages_thread": ticket.messages.all(),
        },
    )


@login_required
@require_GET
def ticket_messages(request, pk: int):
    """HTMX poll endpoint: returns just the messages partial."""
    ticket = get_object_or_404(Ticket, pk=pk)
    if not _user_can_view(ticket, request.user):
        raise Http404
    return render(
        request,
        "support/_messages.html",
        {"ticket": ticket, "messages_thread": ticket.messages.all()},
    )


@login_required
@require_POST
def ticket_reply(request, pk: int):
    ticket = get_object_or_404(Ticket, pk=pk)
    if not _user_can_view(ticket, request.user):
        raise Http404
    form = TicketReplyForm(request.POST)
    if not form.is_valid():
        if request.headers.get("HX-Request"):
            return HttpResponse(status=400)
        return redirect("support:detail", pk=ticket.pk)

    is_staff = request.user.is_staff
    TicketMessage.objects.create(
        ticket=ticket,
        author=request.user,
        body=form.cleaned_data["body"],
        is_from_staff=is_staff,
    )
    ticket.status = (
        Ticket.Status.PENDING_USER if is_staff else Ticket.Status.PENDING_ADMIN
    )
    ticket.save(update_fields=["status", "updated_at"])

    if request.headers.get("HX-Request"):
        return render(
            request,
            "support/_messages.html",
            {"ticket": ticket, "messages_thread": ticket.messages.all()},
        )
    messages.success(request, "Mensaje enviado.")
    return redirect("support:detail", pk=ticket.pk)


# ---------------------------------------------------------------------------
# Verificador de códigos (manual)
# ---------------------------------------------------------------------------

_CODE_REQUEST_RATE_LIMIT = 3
_CODE_REQUEST_WINDOW_MIN = 10


def _client_ip(request) -> str | None:
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if fwd:
        return fwd.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def _too_many_requests(account_email: str, ip: str | None) -> bool:
    """Evita que una misma cuenta o IP abuse del verificador."""
    since = timezone.now() - timedelta(minutes=_CODE_REQUEST_WINDOW_MIN)
    q = CodeRequest.objects.filter(created_at__gte=since)
    by_email = q.filter(account_email__iexact=account_email).count()
    by_ip = q.filter(ip_address=ip).count() if ip else 0
    return max(by_email, by_ip) >= _CODE_REQUEST_RATE_LIMIT


def _resolve_order(order_number: str):
    """Busca un Order por short_uuid o por pk numérico."""
    if not order_number:
        return None
    from orders.models import Order

    token = order_number.strip().lstrip("#")
    if not token:
        return None
    if token.isdigit():
        return Order.objects.filter(pk=int(token)).first()
    return Order.objects.filter(uuid__istartswith=token).first()


def _notify_admins_new_code_request(request, code_request: CodeRequest) -> None:
    """Notifica al canal de distribuidor por Telegram si está configurado."""
    try:
        from orders import telegram as tg
    except Exception:
        return
    if not hasattr(tg, "channel_is_configured"):
        return
    try:
        audience = getattr(tg, "AUDIENCE_DISTRIB", "distrib")
        if not tg.channel_is_configured(audience):
            return
        admin_url = request.build_absolute_uri(
            reverse(
                "admin:support_coderequest_change",
                args=[code_request.pk],
            ),
        )
        label = code_request.get_audience_display()
        text = (
            f"🔔 <b>Nuevo pedido de código</b>\n"
            f"Plataforma: <b>{code_request.get_platform_display()}</b>\n"
            f"Cuenta: <code>{code_request.account_email}</code>\n"
            f"Origen: {label}"
        )
        if code_request.order_number:
            text += f"\nPedido: #{code_request.order_number}"
        buttons = [[{"text": "Responder ahora", "url": admin_url}]]
        # post solo al canal de distribuidor — no al público
        chat_id = tg._distrib_channel_id() if hasattr(tg, "_distrib_channel_id") else None
        if chat_id:
            tg._post_one_channel(chat_id, text, buttons=buttons, photo_url=None)
    except Exception:
        # Nunca fallar la petición del cliente por errores de Telegram.
        return


def _create_code_request(request, *, audience: str):
    """Lógica compartida entre la ruta pública y la del distribuidor."""
    form = CodeRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        account_email = form.cleaned_data["account_email"]
        ip = _client_ip(request)
        if _too_many_requests(account_email, ip):
            form.add_error(
                None,
                "Estás haciendo muchas solicitudes seguidas. Espera unos "
                "minutos antes de intentarlo de nuevo.",
            )
        else:
            cr: CodeRequest = form.save(commit=False)
            cr.audience = audience
            cr.ip_address = ip
            cr.user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:255]
            if request.user.is_authenticated:
                cr.user = request.user
            cr.order = _resolve_order(cr.order_number)
            cr.save()
            _notify_admins_new_code_request(request, cr)
            url = (
                reverse("code_distrib_status", args=[cr.token])
                if audience == CodeRequest.Audience.DISTRIBUTOR
                else reverse("code_status", args=[cr.token])
            )
            return redirect(url)
    return form


@require_GET
def code_request_status_json(request, token: str):
    """Endpoint JSON para el polling del cliente (cada 5 seg)."""
    cr = get_object_or_404(CodeRequest, token=token)
    payload = {
        "status": cr.status,
        "status_label": cr.get_status_display(),
        "code": cr.code if cr.is_delivered else "",
        "code_type": cr.get_code_type_display() if cr.is_delivered and cr.code_type else "",
        "admin_note": cr.admin_note if cr.is_delivered else "",
        "reject_reason": cr.reject_reason if cr.status == cr.Status.REJECTED else "",
        "responded_at": cr.responded_at.isoformat() if cr.responded_at else None,
    }
    return JsonResponse(payload)


def code_request_create(request):
    """Página pública para solicitar un código (clientes finales)."""
    form_or_redirect = _create_code_request(
        request, audience=CodeRequest.Audience.CUSTOMER,
    )
    if not isinstance(form_or_redirect, CodeRequestForm):
        return form_or_redirect
    return render(
        request,
        "support/code_request_form.html",
        {"form": form_or_redirect, "is_distributor": False},
    )


def code_request_status(request, token: str):
    """Página de seguimiento para el cliente final."""
    cr = get_object_or_404(
        CodeRequest, token=token, audience=CodeRequest.Audience.CUSTOMER,
    )
    return render(
        request,
        "support/code_request_status.html",
        {"cr": cr, "is_distributor": False},
    )


@login_required
def code_request_distrib_create(request):
    """Formulario de distribuidor (dentro del panel)."""
    if not (request.user.is_staff or getattr(request.user, "is_distributor", False)):
        raise Http404()
    form_or_redirect = _create_code_request(
        request, audience=CodeRequest.Audience.DISTRIBUTOR,
    )
    if not isinstance(form_or_redirect, CodeRequestForm):
        return form_or_redirect
    recent = CodeRequest.objects.filter(
        audience=CodeRequest.Audience.DISTRIBUTOR, user=request.user,
    )[:20]
    return render(
        request,
        "support/code_request_form.html",
        {"form": form_or_redirect, "is_distributor": True, "recent": recent},
    )


@login_required
def code_request_distrib_status(request, token: str):
    cr = get_object_or_404(
        CodeRequest, token=token, audience=CodeRequest.Audience.DISTRIBUTOR,
    )
    if cr.user_id and cr.user_id != request.user.id and not request.user.is_staff:
        raise Http404()
    return render(
        request,
        "support/code_request_status.html",
        {"cr": cr, "is_distributor": True},
    )
