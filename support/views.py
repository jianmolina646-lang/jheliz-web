from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .forms import TicketCreateForm, TicketReplyForm
from .models import Ticket, TicketMessage


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
