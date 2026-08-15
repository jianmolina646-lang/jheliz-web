"""Formateo de cambios del registro de auditoría."""

import json

def _parse_audit_changes(entry) -> list[dict]:
    """Convierte el JSON `changes` de auditlog en una lista de diffs legibles.

    Cada item: {field, old, new}. Trunca valores muy largos para no romper
    el layout de la tabla.
    """
    raw = getattr(entry, "changes", None)
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return []
    if not isinstance(raw, dict):
        return []
    diffs = []
    for field, change in raw.items():
        if isinstance(change, list) and len(change) == 2:
            old, new = change
        elif isinstance(change, dict):
            old = change.get("old")
            new = change.get("new")
        else:
            old = None
            new = change
        diffs.append({
            "field": field,
            "old": _truncate_for_display(old),
            "new": _truncate_for_display(new),
        })
    return diffs


def _truncate_for_display(value, limit: int = 200) -> str:
    s = "" if value is None else str(value)
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s
