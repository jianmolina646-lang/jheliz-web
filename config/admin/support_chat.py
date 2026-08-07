"""Chat de soporte dentro del panel administrativo."""

from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST


def _admin_context(request, **extra):
    """Contexto base para que la vista herede de admin/base.html."""
    return {
        **admin.site.each_context(request),
        **extra,
    }


def _ticket_template_vars(ticket) -> dict:
    """Dict con las variables que sustituye ReplyTemplate.render para este ticket."""
    user = ticket.user
    order = ticket.order
    nombre = ""
    if user:
        nombre = user.get_full_name() or user.username or ""
    pedido = ""
    telefono = ""
    producto = ""
    if order:
        pedido = order.display_number if hasattr(order, "display_number") else str(order.pk)
        telefono = getattr(order, "phone", "") or ""
        first_item = order.items.first() if hasattr(order, "items") else None
        if first_item:
            producto = getattr(first_item, "product_name", "") or ""
    return {
        "nombre": nombre,
        "pedido": pedido,
        "producto": producto,
        "telefono": telefono,
        "fecha": timezone.localdate().strftime("%d/%m/%Y"),
    }


@staff_member_required
def support_chat_view(request, ticket_id: int):
    """Chat dentro del admin para responder un ticket en formato burbujas."""
    from support.models import ReplyTemplate, Ticket

    ticket = get_object_or_404(
        Ticket.objects.select_related("user", "order"),
        pk=ticket_id,
    )
    templates = ReplyTemplate.objects.filter(is_active=True).order_by("category", "name")
    ctx = _admin_context(
        request,
        ticket=ticket,
        messages_thread=ticket.messages.all(),
        messages_poll_url=reverse("admin_support_chat_messages", args=[ticket.pk]),
        reply_templates=templates,
        chat_vars=_ticket_template_vars(ticket),
        title=f"Chat — Ticket #{ticket.pk}",
    )
    return render(request, "admin/support/chat.html", ctx)


@staff_member_required
@require_POST
def support_chat_reply(request, ticket_id: int):
    """Crea un TicketMessage del staff. HTMX-aware: devuelve el partial."""
    from support.models import ReplyTemplate, Ticket, TicketMessage

    ticket = get_object_or_404(Ticket, pk=ticket_id)
    body = (request.POST.get("body") or "").strip()
    template_id = request.POST.get("template_id") or ""
    if template_id.isdigit():
        tpl = ReplyTemplate.objects.filter(pk=int(template_id), is_active=True).first()
        if tpl and not body:
            body = tpl.render(ticket=ticket)
        if tpl:
            tpl.use_count = F("use_count") + 1
            tpl.last_used_at = timezone.now()
            tpl.save(update_fields=["use_count", "last_used_at"])

    if not body:
        if request.headers.get("HX-Request"):
            return HttpResponse(status=400)
        messages.error(request, "El mensaje no puede estar vacío.")
        return redirect("admin_support_chat", ticket_id=ticket.pk)

    TicketMessage.objects.create(
        ticket=ticket, author=request.user, body=body, is_from_staff=True,
    )
    ticket.status = Ticket.Status.PENDING_USER
    ticket.save(update_fields=["status", "updated_at"])

    if request.headers.get("HX-Request"):
        return render(
            request,
            "support/_messages.html",
            {
                "ticket": ticket,
                "messages_thread": ticket.messages.all(),
                "messages_poll_url": reverse(
                    "admin_support_chat_messages", args=[ticket.pk]
                ),
            },
        )
    messages.success(request, "Respuesta enviada al cliente.")
    return redirect("admin_support_chat", ticket_id=ticket.pk)


@staff_member_required
def support_chat_messages(request, ticket_id: int):
    """HTMX poll endpoint del admin: devuelve solo el partial."""
    from support.models import Ticket

    ticket = get_object_or_404(Ticket, pk=ticket_id)
    return render(
        request,
        "support/_messages.html",
        {
            "ticket": ticket,
            "messages_thread": ticket.messages.all(),
            "messages_poll_url": reverse(
                "admin_support_chat_messages", args=[ticket.pk]
            ),
        },
    )
