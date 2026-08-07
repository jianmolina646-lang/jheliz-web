"""Plantillas de respuesta del panel administrativo."""

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse


@staff_member_required
def reply_templates_json(request):
    """Devuelve las plantillas activas, con body renderizado si se pasa
    `?ticket_id=N` (sustituye {nombre}, {pedido}, etc).
    """
    from support.models import ReplyTemplate, Ticket

    ticket = None
    ticket_id = request.GET.get("ticket_id")
    if ticket_id and ticket_id.isdigit():
        ticket = Ticket.objects.filter(pk=int(ticket_id)).select_related("user", "order").first()

    out = []
    for t in ReplyTemplate.objects.filter(is_active=True).order_by("category", "name"):
        out.append({
            "id": t.pk,
            "name": t.name,
            "category": t.category,
            "category_label": t.get_category_display(),
            "subject": t.subject,
            "body_rendered": t.render(ticket=ticket),
        })
    return JsonResponse({"templates": out})
