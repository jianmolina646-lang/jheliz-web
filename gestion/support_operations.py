from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import SupportMessage, SupportTicket


@transaction.atomic
def create_ticket(contact, category, text, subscription=None, telegram_message_id=None):
    owner_id = contact.owner_id
    # Bloquea la fila del contacto para serializar la numeración por revendedor.
    type(contact).objects.select_for_update().get(pk=contact.pk)
    last = (
        SupportTicket.objects.filter(owner_id=owner_id)
        .aggregate(value=Max("number"))["value"] or 0
    )
    ticket = SupportTicket.objects.create(
        owner_id=owner_id,
        client_id=contact.client_id,
        subscription=subscription,
        number=last + 1,
        category=category,
        subject=text.strip()[:160],
        customer_chat_id=contact.telegram_chat_id,
    )
    SupportMessage.objects.create(
        ticket=ticket,
        sender=SupportMessage.Sender.CUSTOMER,
        text=text.strip(),
        telegram_message_id=telegram_message_id,
    )
    return ticket


@transaction.atomic
def add_message(ticket, sender, text, telegram_message_id=None):
    message = SupportMessage.objects.create(
        ticket=ticket,
        sender=sender,
        text=text.strip(),
        telegram_message_id=telegram_message_id,
    )
    ticket.last_message_at = timezone.now()
    if sender == SupportMessage.Sender.AGENT:
        ticket.status = SupportTicket.Status.WAITING
    elif sender == SupportMessage.Sender.CUSTOMER and ticket.status != SupportTicket.Status.NEW:
        ticket.status = SupportTicket.Status.OPEN
    ticket.save(update_fields=["last_message_at", "status", "updated_at"])
    return message


def set_status(ticket, status):
    if status not in SupportTicket.Status.values:
        return False
    ticket.status = status
    ticket.resolved_at = timezone.now() if status == SupportTicket.Status.RESOLVED else None
    ticket.save(update_fields=["status", "resolved_at", "updated_at"])
    return True
