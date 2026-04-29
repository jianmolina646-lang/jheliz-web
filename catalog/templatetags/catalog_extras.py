"""Filtros para gradientes/colores deterministas a partir del slug del producto.

Si un producto no tiene imagen, generamos un fondo bonito a partir de un hash
estable del slug — el mismo producto siempre tiene el mismo color.
"""
import hashlib

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


# Paletas curadas (más cercanas a los colores oficiales de las marcas que vendemos).
_PALETTES = [
    ("#E50914", "#831010"),  # Netflix red
    ("#0072d2", "#1e3a8a"),  # Disney+ blue
    ("#1DB954", "#065f46"),  # Spotify green
    ("#00A8E1", "#1d4ed8"),  # Prime blue
    ("#7c3aed", "#4c1d95"),  # Max purple
    ("#FF0000", "#7f1d1d"),  # YouTube red
    ("#F47521", "#7c2d12"),  # Crunchyroll orange
    ("#10A37F", "#064e3b"),  # ChatGPT teal
    ("#D83B01", "#7c2d12"),  # Office orange
    ("#0d6efd", "#1e293b"),  # Generic blue
    ("#7D2AE7", "#312e81"),  # Canva purple
    ("#ec4899", "#831843"),  # Jheliz pink
    ("#f59e0b", "#78350f"),  # Amber
    ("#06b6d4", "#155e75"),  # Cyan
]


def _palette_for(seed: str) -> tuple[str, str]:
    """Devuelve un par (color1, color2) determinista basado en un hash del seed."""
    if not seed:
        return _PALETTES[0]
    digest = hashlib.md5(seed.encode("utf-8")).digest()
    idx = digest[0] % len(_PALETTES)
    return _PALETTES[idx]


@register.simple_tag
def product_gradient(product) -> str:
    """Devuelve un `background:` CSS para usar como banner del producto.

    Útil cuando el producto no tiene imagen — produce un degradado distinto y
    consistente por slug.
    """
    seed = (getattr(product, "slug", "") or getattr(product, "name", "") or "x")
    c1, c2 = _palette_for(seed)
    css = (
        f"background: radial-gradient(120% 80% at 20% 0%, {c1}, transparent 60%),"
        f" radial-gradient(120% 80% at 80% 100%, {c2}, transparent 60%),"
        f" linear-gradient(135deg, {c2}, #0b0217);"
    )
    return mark_safe(css)


@register.simple_tag
def product_accent(product) -> str:
    """Color principal del producto (para chips, ribbons, etc.)."""
    seed = (getattr(product, "slug", "") or getattr(product, "name", "") or "x")
    c1, _ = _palette_for(seed)
    return c1


@register.filter
def cheapest_plan_for(product, user):
    """Plan m\u00e1s barato visible al usuario, ignorando precios en S/ 0.

    Usa `Product.cheapest_visible_plan(user)` para mostrar el `DESDE`
    correcto en cards y SEO, evitando que un plan en 0 lo contamine.
    """
    if product is None:
        return None
    return product.cheapest_visible_plan(user)
