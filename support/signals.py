import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.loader import render_to_string

from .models import TicketMessage

logger = logging.getLogger(__name__)


@receiver(post_save, sender=TicketMessage)
def _notify_ticket_message(sender, instance: TicketMessage, created: bool, **kwargs):
    if not created:
        return
    ticket = instance.ticket
    try:
        if instance.is_from_staff:
            # Notificar al dueño del ticket que hay respuesta nueva
            recipient = ticket.user.email
            if not recipient:
                return
            html = render_to_string(
                "emails/ticket_staff_reply.html",
                {"ticket": ticket, "message": instance},
            )
            send_mail(
                subject=f"Nueva respuesta en tu ticket #{ticket.id} — {ticket.subject}",
                message=f"Te respondimos el ticket #{ticket.id}. Entra a jhelizservicestv.xyz para leer.",
                from_email=None,
                recipient_list=[recipient],
                html_message=html,
                fail_silently=True,
            )
        else:
            # Notificar al equipo de soporte
            admin_email = getattr(settings, "SUPPORT_ADMIN_EMAIL", "")
            if not admin_email:
                admin_email = getattr(settings, "DEFAULT_FROM_EMAIL", "")
            if not admin_email:
                return
            html = render_to_string(
                "emails/ticket_user_message.html",
                {"ticket": ticket, "message": instance},
            )
            send_mail(
                subject=f"[Jheliz Soporte] Ticket #{ticket.id} — {ticket.subject}",
                message=f"{ticket.user.username}: {instance.body[:200]}",
                from_email=None,
                recipient_list=[admin_email],
                html_message=html,
                fail_silently=True,
            )
    except Exception:
        logger.exception("No se pudo notificar mensaje de ticket")
