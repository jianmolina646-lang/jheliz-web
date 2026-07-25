"""Utilidades de fechas compartidas por ventas y control de suscripciones."""

from calendar import monthrange
from datetime import datetime, timedelta


def add_service_duration(start: datetime, days: int) -> datetime:
    """
    Suma la duración comercial conservando el día del mes.

    Los planes configurados en bloques de 30 días representan meses
    comerciales: 30 = 1 mes, 60 = 2 meses, 90 = 3 meses. Así, una cuenta
    iniciada el 12 de julio vence el 12 de agosto. Para días que no forman
    meses completos se conserva el cálculo exacto por días.

    Si el día no existe en el mes destino, se usa su último día
    (31 de enero + 1 mes = 28/29 de febrero).
    """

    duration = int(days)
    if duration <= 0:
        return start
    if duration % 30:
        return start + timedelta(days=duration)

    months = duration // 30
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day)
