"""Búsqueda global del panel administrativo."""

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.template.response import TemplateResponse


def _perform_global_search(q: str, limit: int):
    """Ejecuta la búsqueda cruzada y devuelve un dict con los grupos encontrados.

    Se usa tanto desde el endpoint JSON (modal Cmd+K) como desde la página
    de resultados HTML (`/panel-jheliz-control/search/?q=...&full=1`).
    """
    from django.urls import reverse as _reverse
    from django.db.models import Q
    from django.db.models.functions import Cast
    from django.db.models import CharField as _CharField

    from accounts.models import User
    from catalog.models import Plan, Product
    from orders.models import Order
    from support.models import Ticket

    q = (q or "").strip()
    empty = {"orders": [], "customers": [], "products": [], "plans": [], "tickets": []}
    if len(q) < 2:
        return empty

    # Pedidos: uuid (string), email, teléfono, referencia, telegram, notas.
    # UUIDField no matchea bien con icontains en todos los backends; casteamos
    # a CharField para búsquedas parciales reales.
    order_qs = Order.objects.annotate(uuid_str=Cast("uuid", _CharField()))
    order_filter = (
        Q(email__icontains=q)
        | Q(phone__icontains=q)
        | Q(payment_reference__icontains=q)
        | Q(telegram_username__icontains=q)
        | Q(notes__icontains=q)
        | Q(uuid_str__icontains=q)
    )
    orders = []
    for o in order_qs.filter(order_filter).order_by("-created_at")[:limit]:
        orders.append({
            "label": f"Pedido {str(o.uuid)[:8]} — {o.email or o.phone or o.telegram_username or '—'}",
            "meta": f"{o.get_status_display()} · {o.currency} {o.total or 0}",
            "url": _reverse("admin:orders_order_change", args=[o.pk]),
        })

    # Clientes / distribuidores
    user_filter = (
        Q(username__icontains=q)
        | Q(email__icontains=q)
        | Q(first_name__icontains=q)
        | Q(last_name__icontains=q)
        | Q(phone__icontains=q)
        | Q(telegram_username__icontains=q)
    )
    customers = []
    for u in User.objects.filter(user_filter).order_by("-id")[:limit]:
        full = u.get_full_name() or u.username
        role = u.get_role_display() if hasattr(u, "get_role_display") else ""
        meta_parts = [p for p in [u.email, role] if p]
        customers.append({
            "label": full,
            "meta": " · ".join(meta_parts),
            "url": _reverse("admin:accounts_user_change", args=[u.pk]),
        })

    # Productos
    products = []
    for p in Product.objects.filter(
        Q(name__icontains=q) | Q(slug__icontains=q),
    ).order_by("-id")[:limit]:
        products.append({
            "label": p.name,
            "meta": "activo" if p.is_active else "inactivo",
            "url": _reverse("admin:catalog_product_change", args=[p.pk]),
        })

    # Planes
    plans = []
    for pl in (
        Plan.objects.filter(name__icontains=q)
        .select_related("product").order_by("-id")[:limit]
    ):
        plans.append({
            "label": f"{pl.product.name} — {pl.name}" if pl.product else pl.name,
            "meta": f"{pl.currency} {pl.price}",
            "url": _reverse("admin:catalog_plan_change", args=[pl.pk]),
        })

    # Tickets
    ticket_filter = Q(subject__icontains=q)
    if hasattr(Ticket, "code"):
        ticket_filter |= Q(code__icontains=q)
    tickets = []
    for t in Ticket.objects.filter(ticket_filter).order_by("-created_at")[:limit]:
        tickets.append({
            "label": t.subject or f"Ticket #{t.pk}",
            "meta": t.get_status_display() if hasattr(t, "get_status_display") else "",
            "url": _reverse("admin:support_ticket_change", args=[t.pk]),
        })

    return {
        "orders": orders,
        "customers": customers,
        "products": products,
        "plans": plans,
        "tickets": tickets,
    }


@staff_member_required
def global_search(request):
    """Búsqueda cruzada en el admin.

    Dos modos de respuesta:
    - JSON (default, usado por el modal Cmd+K con top 5 por sección).
    - HTML cuando se pasa ``?full=1``: página de resultados con top 25 por
      sección, pensada para cuando el modal no alcanza.
    """
    q = (request.GET.get("q") or "").strip()
    full = request.GET.get("full") == "1"
    limit = 25 if full else 5
    groups = _perform_global_search(q, limit=limit)

    if full:
        total = sum(len(v) for v in groups.values())
        context = {
            **admin.site.each_context(request),
            "title": f"Búsqueda global: {q}" if q else "Búsqueda global",
            "q": q,
            "groups": groups,
            "total": total,
            "limit": limit,
        }
        return TemplateResponse(
            request, "admin/global_search_results.html", context,
        )
    return JsonResponse(groups)
