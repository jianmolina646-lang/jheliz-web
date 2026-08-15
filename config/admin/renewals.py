"""Listado de renovaciones pendientes del panel administrativo."""

from datetime import timedelta

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone


def _admin_context(request, **extra):
    """Contexto base para que la vista herede de admin/base.html."""
    return {
        **admin.site.each_context(request),
        **extra,
    }


_RENEWAL_WINDOWS = {
    "expired": ("Vencidos",       -180, 0,  "error",            "danger"),
    "today":   ("Vencen hoy",     0,    1,  "today",            "warning"),
    "3d":      ("Próx. 3 días",   0,    4,  "alarm",            "warning"),
    "7d":      ("Próx. 7 días",   0,    8,  "calendar_today",   "info"),
    "30d":     ("Próx. 30 días",  0,    31, "event_repeat",     "success"),
}


@staff_member_required
def renewals_view(request):
    """Lista items próximos a vencer agrupados por filtro de ventana."""
    from orders.models import Order, OrderItem

    window_key = request.GET.get("w", "7d")
    if window_key not in _RENEWAL_WINDOWS:
        window_key = "7d"
    label, start_offset, end_offset, _icon, _tone = _RENEWAL_WINDOWS[window_key]

    now = timezone.now()
    paid_statuses = (
        Order.Status.PAID, Order.Status.PREPARING, Order.Status.DELIVERED,
    )

    def _window_qs(s_off: int, e_off: int):
        s = now + timedelta(days=s_off) if s_off < 0 else now
        e = now + timedelta(days=e_off)
        return OrderItem.objects.filter(
            expires_at__isnull=False,
            expires_at__gte=s,
            expires_at__lt=e,
            order__status__in=paid_statuses,
        )

    # Conteos por ventana para mostrar en los chips de filtro.
    window_counts = {
        key: _window_qs(s_off, e_off).count()
        for key, (_lbl, s_off, e_off, _ic, _to) in _RENEWAL_WINDOWS.items()
    }

    # Estructura "rica" para el template — más fácil de iterar con todos
    # los metadatos del chip (label, count, ícono, tono, key).
    windows_rich = [
        {
            "key": key,
            "label": lbl,
            "icon": ic,
            "tone": to,
            "count": window_counts.get(key, 0),
            "active": (window_key == key),
        }
        for key, (lbl, _s, _e, ic, to) in _RENEWAL_WINDOWS.items()
    ]

    qs = (
        _window_qs(start_offset, end_offset)
        .select_related("order", "order__user", "product", "plan")
        .order_by("expires_at")
    )

    items = []
    for it in qs[:200]:
        days_left = (it.expires_at - now).days if it.expires_at else None
        # Tono semafórico para el chip "Días" (alineado con el de filtros).
        if days_left is None:
            d_tone, d_icon = "neutral", "schedule"
        elif days_left < 0:
            d_tone, d_icon = "danger", "error"
        elif days_left == 0:
            d_tone, d_icon = "danger", "today"
        elif days_left <= 1:
            d_tone, d_icon = "warning", "alarm"
        elif days_left <= 3:
            d_tone, d_icon = "warning", "schedule"
        elif days_left <= 7:
            d_tone, d_icon = "info", "calendar_today"
        else:
            d_tone, d_icon = "success", "event_available"

        items.append({
            "id": it.pk,
            "order_id": it.order_id,
            "order_short": str(it.order.uuid)[:8] if it.order.uuid else "",
            "customer_email": it.order.email or "",
            "customer_phone": it.order.phone or "",
            "product_name": it.product_name,
            "plan_name": it.plan_name,
            "expires_at": it.expires_at,
            "days_left": days_left,
            "days_tone": d_tone,
            "days_icon": d_icon,
            "reminder_7d": bool(it.expiry_reminder_7d_sent_at),
            "reminder_3d": bool(it.expiry_reminder_3d_sent_at),
            "reminder_1d": bool(it.expiry_reminder_1d_sent_at),
            "reminder_0d": bool(it.expiry_reminder_0d_sent_at),
            "order_change_url": reverse("admin:orders_order_change", args=[it.order_id]),
            "renew_url": reverse("admin_renew_item", args=[it.pk]),
            "whatsapp_url": _whatsapp_link(it),
        })

    ctx = _admin_context(
        request,
        title="Renovaciones pendientes",
        items=items,
        window_key=window_key,
        window_label=label,
        windows=_RENEWAL_WINDOWS,
        windows_rich=windows_rich,
        window_counts=window_counts,
        total_items=sum(window_counts.values()),
    )
    return render(request, "admin/renewals.html", ctx)


def _whatsapp_link(item) -> str:
    """Genera un link wa.me con texto pre-rellenado para invitar al cliente
    a renovar con 1 click (magic link).
    """
    import urllib.parse
    from django.conf import settings as dj_settings

    phone = (item.order.phone or "").strip().replace(" ", "").replace("+", "")
    if not phone:
        return ""
    if not phone.startswith("51") and len(phone) == 9:
        phone = "51" + phone
    fecha = item.expires_at.strftime("%d/%m/%Y") if item.expires_at else ""

    site_url = getattr(dj_settings, "SITE_URL", "").rstrip("/")
    renew_link = (
        f"{site_url}/renovar/t/{item.renewal_token}/"
        if item.renewal_token else ""
    )
    txt_lines = [
        f"Hola! Te recordamos que tu *{item.product_name} ({item.plan_name})* "
        f"vence el {fecha}.",
    ]
    if renew_link:
        txt_lines.append(f"Renueva con 1 click aquí 👉 {renew_link}")
    else:
        txt_lines.append("¿Quieres renovarlo? Te paso el link de pago.")
    txt = "\n\n".join(txt_lines)
    return f"https://wa.me/{phone}?text={urllib.parse.quote(txt)}"
