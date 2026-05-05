"""Helpers visuales para los admins de Usuarios / Clientes / Distribuidores.

Generan HTML reutilizable con las mismas clases que usa el resto del panel
moderno (Unfold v6 + jheliz_polish.css):
- avatar con iniciales y color determinístico
- chips de estado coloridos
- stat cards con icono
- celda combinada (avatar + nombre + email) para changelist
- tabla "moderna" para historiales
- enlaces de acción rápida (WhatsApp / Telegram / Mail)
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Iterable

from django.utils import timezone
from django.utils.html import escape, format_html
from django.utils.safestring import SafeString


# Paleta determinística para avatares (degradados pastel sobre fondo oscuro).
_AVATAR_GRADIENTS: list[tuple[str, str]] = [
    ("#f472b6", "#a855f7"),  # rosa → violeta
    ("#34d399", "#0ea5e9"),  # verde → celeste
    ("#fb7185", "#f59e0b"),  # rosa → ámbar
    ("#a78bfa", "#3b82f6"),  # violeta → azul
    ("#fbbf24", "#ef4444"),  # ámbar → rojo
    ("#22d3ee", "#6366f1"),  # cyan → indigo
    ("#84cc16", "#14b8a6"),  # lima → teal
    ("#ec4899", "#8b5cf6"),  # fucsia → violeta
]


def _avatar_colors(seed: str) -> tuple[str, str]:
    h = hashlib.md5(seed.encode("utf-8")).digest()
    return _AVATAR_GRADIENTS[h[0] % len(_AVATAR_GRADIENTS)]


def _initials(user) -> str:
    name = (user.get_full_name() or "").strip() or user.username or user.email or "?"
    parts = [p for p in name.replace(".", " ").replace("_", " ").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def avatar_html(user, size: int = 36) -> SafeString:
    """Avatar circular con iniciales y degradado determinístico."""
    seed = (user.email or user.username or "?")
    c1, c2 = _avatar_colors(seed)
    return format_html(
        '<span class="jh-avatar" style="--s:{}px;--g1:{};--g2:{}">{}</span>',
        size, c1, c2, _initials(user),
    )


def user_card_cell(user, *, sub: str | None = None) -> SafeString:
    """Celda combinada para changelist: avatar + nombre + email/sub."""
    name = user.get_full_name() or user.username
    sub = sub if sub is not None else (user.email or "—")
    return format_html(
        '<div class="jh-user-cell">{avatar}'
        '<div class="jh-user-cell__txt">'
        '<div class="jh-user-cell__name">{name}</div>'
        '<div class="jh-user-cell__sub">{sub}</div>'
        '</div></div>',
        avatar=avatar_html(user, size=34),
        name=escape(name),
        sub=escape(sub or "—"),
    )


# ---------------------------------------------------------------------------
# Chips
# ---------------------------------------------------------------------------

_CHIP_STYLES: dict[str, tuple[str, str]] = {
    "success":  ("rgba(16,185,129,.15)", "#34d399"),
    "warning":  ("rgba(245,158,11,.15)", "#fbbf24"),
    "danger":   ("rgba(244, 63, 94,.15)", "#fb7185"),
    "info":     ("rgba(56,189,248,.15)", "#38bdf8"),
    "violet":   ("rgba(168, 85,247,.15)", "#c4b5fd"),
    "pink":     ("rgba(236, 72,153,.15)", "#f9a8d4"),
    "neutral":  ("rgba(148,163,184,.15)", "#cbd5e1"),
}


def chip(text: str, *, tone: str = "neutral", icon: str | None = None) -> SafeString:
    bg, fg = _CHIP_STYLES.get(tone, _CHIP_STYLES["neutral"])
    icon_html = (
        format_html(
            '<span class="material-symbols-outlined" style="font-size:14px;'
            'margin-right:4px;vertical-align:-2px">{}</span>',
            icon,
        )
        if icon else ""
    )
    return format_html(
        '<span class="jh-chip" style="background:{};color:{}">{}{}</span>',
        bg, fg, icon_html, escape(text),
    )


def chips(items: Iterable[tuple[str, str]]) -> SafeString:
    """items: lista de tuplas (texto, tone)."""
    parts = [chip(t, tone=tone) for t, tone in items]
    return format_html('<div class="jh-chips">{}</div>', format_html("".join(parts)))


# ---------------------------------------------------------------------------
# Tiempo relativo (ej. "hace 3 días")
# ---------------------------------------------------------------------------

def time_ago(dt) -> str:
    if dt is None:
        return "—"
    now = timezone.now()
    delta = now - dt
    if delta < timedelta(minutes=1):
        return "ahora mismo"
    if delta < timedelta(hours=1):
        m = int(delta.total_seconds() // 60)
        return f"hace {m} min"
    if delta < timedelta(days=1):
        h = int(delta.total_seconds() // 3600)
        return f"hace {h} h"
    if delta < timedelta(days=30):
        d = delta.days
        return f"hace {d} día{'s' if d != 1 else ''}"
    if delta < timedelta(days=365):
        mo = delta.days // 30
        return f"hace {mo} mes{'es' if mo != 1 else ''}"
    y = delta.days // 365
    return f"hace {y} año{'s' if y != 1 else ''}"


# ---------------------------------------------------------------------------
# Stat cards
# ---------------------------------------------------------------------------

def stat_grid(cards: list[dict]) -> SafeString:
    """Grid de tarjetas con métricas.

    cards: lista de dicts con keys:
        - label (str): título corto en uppercase
        - value (str): número grande
        - sub (str, opcional): texto chico debajo
        - tone (str, opcional): "emerald" | "cyan" | "violet" | "pink" | "amber"
        - icon (str, opcional): nombre de material icon
    """
    tones = {
        "emerald": "from-emerald-500/15",
        "cyan":    "from-cyan-500/15",
        "violet":  "from-violet-500/15",
        "pink":    "from-pink-500/15",
        "amber":   "from-amber-500/15",
    }
    pieces = []
    for c in cards:
        tone_cls = tones.get(c.get("tone", "violet"), tones["violet"])
        icon = c.get("icon")
        icon_html = (
            f'<span class="material-symbols-outlined jh-stat__icon">{escape(icon)}</span>'
            if icon else ""
        )
        sub = c.get("sub")
        sub_html = (
            f'<div class="jh-stat__sub">{escape(sub)}</div>'
            if sub else ""
        )
        pieces.append(
            f'<div class="jh-stat {tone_cls}">'
            f'  <div class="jh-stat__head">'
            f'    <div class="jh-stat__label">{escape(c["label"])}</div>'
            f'    {icon_html}'
            f'  </div>'
            f'  <div class="jh-stat__value">{escape(c["value"])}</div>'
            f'  {sub_html}'
            f'</div>'
        )
    return format_html('<div class="jh-stat-grid">{}</div>', format_html("".join(pieces)))


# ---------------------------------------------------------------------------
# Acciones de contacto rápido (WhatsApp / Mail / Telegram)
# ---------------------------------------------------------------------------

def contact_actions(user) -> SafeString:
    parts = []
    if user.phone:
        digits = "".join(c for c in user.phone if c.isdigit())
        if digits:
            parts.append(
                f'<a class="jh-act jh-act--wa" href="https://wa.me/{escape(digits)}" '
                f'target="_blank" rel="noopener" title="Abrir WhatsApp">'
                f'<span class="material-symbols-outlined">chat</span></a>'
            )
    if user.email:
        parts.append(
            f'<a class="jh-act jh-act--mail" href="mailto:{escape(user.email)}" '
            f'title="Enviar email">'
            f'<span class="material-symbols-outlined">mail</span></a>'
        )
    tg = (user.telegram_username or "").lstrip("@") if hasattr(user, "telegram_username") else ""
    if tg:
        parts.append(
            f'<a class="jh-act jh-act--tg" href="https://t.me/{escape(tg)}" '
            f'target="_blank" rel="noopener" title="Abrir Telegram">'
            f'<span class="material-symbols-outlined">send</span></a>'
        )
    if not parts:
        return format_html('<span class="jh-muted">—</span>')
    return format_html('<div class="jh-actions">{}</div>', format_html("".join(parts)))


# ---------------------------------------------------------------------------
# Tabla moderna con header sticky
# ---------------------------------------------------------------------------

def modern_table(headers: list[str], rows: list[list[SafeString | str]]) -> SafeString:
    if not rows:
        return format_html('<div class="jh-empty">Sin registros aún.</div>')
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body_rows = []
    for r in rows:
        cells = "".join(
            f"<td>{c if isinstance(c, SafeString) else escape(str(c))}</td>"
            for c in r
        )
        body_rows.append(f"<tr>{cells}</tr>")
    return format_html(
        '<div class="jh-table-wrap"><table class="jh-table">'
        '<thead><tr>{}</tr></thead><tbody>{}</tbody></table></div>',
        format_html(head),
        format_html("".join(body_rows)),
    )
