"""Carrito de compras basado en sesi\u00f3n.

Guarda los items como una lista de dicts en request.session['cart'], cada uno con:
    {
        "plan_id": int,
        "quantity": int,
        "profile_name": str,
        "pin": str,
        "notes": str,
    }
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterator

from catalog.models import Plan

CART_SESSION_KEY = "cart"
CART_COUPON_SESSION_KEY = "cart_coupon_code"

# Descuentos por armar un combo (productos distintos en el carrito).
# Solo para cliente final — el distribuidor ya tiene su propio precio mayorista.
COMBO_DISCOUNT_TIERS = {
    2: Decimal("0.10"),   # 10% con 2 productos distintos
    3: Decimal("0.15"),   # 15% con 3+
}


def combo_tier_percent(distinct_products: int) -> Decimal:
    """Devuelve el % de descuento para N productos distintos."""
    if distinct_products >= 3:
        return COMBO_DISCOUNT_TIERS[3]
    if distinct_products == 2:
        return COMBO_DISCOUNT_TIERS[2]
    return Decimal("0.00")


@dataclass
class CartLine:
    plan: Plan
    quantity: int
    profile_name: str
    pin: str
    notes: str
    index: int

    @property
    def unit_price(self) -> Decimal:
        return self.plan.price_customer

    def price_for(self, user) -> Decimal:
        return self.plan.price_for(user)

    def subtotal_for(self, user) -> Decimal:
        return self.price_for(user) * self.quantity


class Cart:
    """Wrapper sobre request.session con utilidades del carrito."""

    def __init__(self, request) -> None:
        self.session = request.session
        self.user = request.user
        data = self.session.get(CART_SESSION_KEY)
        if not isinstance(data, list):
            data = []
        self._items: list[dict] = data

    # ----- persistencia -----

    def save(self) -> None:
        self.session[CART_SESSION_KEY] = self._items
        self.session.modified = True

    def clear(self) -> None:
        self._items = []
        self.save()
        self.session.pop(CART_COUPON_SESSION_KEY, None)
        self.session.modified = True

    # ----- operaciones -----

    def add(
        self,
        plan: Plan,
        quantity: int = 1,
        profile_name: str = "",
        pin: str = "",
        notes: str = "",
    ) -> None:
        self._items.append(
            {
                "plan_id": plan.pk,
                "quantity": max(1, int(quantity)),
                "profile_name": profile_name.strip()[:60],
                "pin": pin.strip()[:8],
                "notes": notes.strip()[:500],
            }
        )
        self.save()

    def remove(self, index: int) -> None:
        if 0 <= index < len(self._items):
            del self._items[index]
            self.save()

    def update_line(self, index: int, **fields) -> None:
        if 0 <= index < len(self._items):
            for key in ("profile_name", "pin", "notes"):
                if key in fields:
                    self._items[index][key] = str(fields[key]).strip()
            if "quantity" in fields:
                self._items[index]["quantity"] = max(1, int(fields["quantity"]))
            self.save()

    # ----- queries -----

    def lines(self) -> Iterator[CartLine]:
        if not self._items:
            return
        plan_ids = [it["plan_id"] for it in self._items]
        plans = {p.pk: p for p in Plan.objects.filter(pk__in=plan_ids).select_related("product")}
        for idx, it in enumerate(self._items):
            plan = plans.get(it["plan_id"])
            if plan is None:
                continue
            yield CartLine(
                plan=plan,
                quantity=it["quantity"],
                profile_name=it.get("profile_name", ""),
                pin=it.get("pin", ""),
                notes=it.get("notes", ""),
                index=idx,
            )

    def __iter__(self):
        return self.lines()

    def __len__(self) -> int:
        return sum(it["quantity"] for it in self._items)

    def is_empty(self) -> bool:
        return not self._items

    def subtotal_for(self, user) -> Decimal:
        total = Decimal("0.00")
        for line in self.lines():
            total += line.subtotal_for(user)
        return total

    def total_for(self, user) -> Decimal:
        """Devuelve el total con descuento de cupón y combo aplicados."""
        base = self.subtotal_for(user)
        return base - self.discount_for(user) - self.combo_discount_for(user)

    # ----- Combo (auto-descuento por productos distintos) -----

    def distinct_product_count(self) -> int:
        """Cantidad de productos distintos en el carrito (no planes, no unidades)."""
        seen = set()
        for line in self.lines():
            if line.plan and line.plan.product_id:
                seen.add(line.plan.product_id)
        return len(seen)

    def combo_tier_percent(self) -> Decimal:
        """% de descuento automático por armar un combo. 0 si el usuario es distribuidor."""
        if self.user and getattr(self.user, "is_distributor", False):
            return Decimal("0.00")
        return combo_tier_percent(self.distinct_product_count())

    def combo_discount_for(self, user) -> Decimal:
        """Descuento absoluto (Soles) por el combo. Aplica sobre el subtotal post-cupón."""
        pct = self.combo_tier_percent()
        if pct <= 0:
            return Decimal("0.00")
        base = self.subtotal_for(user) - self.discount_for(user)
        if base <= 0:
            return Decimal("0.00")
        discount = (base * pct).quantize(Decimal("0.01"))
        return discount

    # ----- Cupones -----

    def get_coupon_code(self) -> str:
        return (self.session.get(CART_COUPON_SESSION_KEY) or "").upper().strip()

    def get_coupon(self):
        """Devuelve el Coupon (si existe y está activo). Lazy import para evitar ciclos."""
        code = self.get_coupon_code()
        if not code:
            return None
        from .models import Coupon

        return Coupon.objects.filter(code=code).first()

    def set_coupon_code(self, code: str) -> None:
        self.session[CART_COUPON_SESSION_KEY] = code.upper().strip() if code else ""
        self.session.modified = True

    def clear_coupon(self) -> None:
        self.session.pop(CART_COUPON_SESSION_KEY, None)
        self.session.modified = True

    def discount_for(self, user) -> Decimal:
        coupon = self.get_coupon()
        if not coupon:
            return Decimal("0.00")
        subtotal = self.subtotal_for(user)
        ok, _ = coupon.is_eligible_for(user, subtotal)
        if not ok:
            return Decimal("0.00")
        return coupon.compute_discount(subtotal)
