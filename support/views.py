from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

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


@login_required
def ticket_detail(request, pk: int):
    ticket = get_object_or_404(Ticket, pk=pk)
    if ticket.user_id != request.user.id and not request.user.is_staff:
        raise Http404
    reply_form = TicketReplyForm()
    return render(
        request,
        "support/ticket_detail.html",
        {"ticket": ticket, "reply_form": reply_form, "messages_thread": ticket.messages.all()},
    )


@login_required
@require_POST
def ticket_reply(request, pk: int):
    ticket = get_object_or_404(Ticket, pk=pk)
    if ticket.user_id != request.user.id and not request.user.is_staff:
        raise Http404
    form = TicketReplyForm(request.POST)
    if form.is_valid():
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
        messages.success(request, "Mensaje enviado.")
    return redirect("support:detail", pk=ticket.pk)
