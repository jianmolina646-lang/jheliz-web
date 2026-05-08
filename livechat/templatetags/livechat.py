"""Template tags del live chat — usados por el widget público."""

from __future__ import annotations

from django import template
from django.utils import timezone

register = template.Library()


# Horarios "online" del operador (hora Lima, 24h). Si el visitante escribe
# fuera de este rango le mostramos un cartel "fuera de horario".
ONLINE_HOUR_FROM = 9
ONLINE_HOUR_TO = 23  # excluyente: 23:00 ya es offline


@register.simple_tag
def livechat_is_online() -> bool:
    """¿Estamos en horario de soporte? Devuelve ``True`` si sí.

    Usa ``timezone.localtime()`` que respeta ``settings.TIME_ZONE``
    (``America/Lima`` en este proyecto).
    """
    now = timezone.localtime()
    return ONLINE_HOUR_FROM <= now.hour < ONLINE_HOUR_TO
