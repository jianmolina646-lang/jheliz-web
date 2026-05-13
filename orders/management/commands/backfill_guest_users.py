"""Backfill: vincula pedidos guest históricos a un User cliente.

Recorre los ``Order`` con ``user=None`` y crea (o reutiliza) un ``User``
por email, para que los compradores que pagaron como invitado aparezcan
retroactivamente en la sección "Zona de clientes" del admin.

Uso::

    python manage.py backfill_guest_users           # aplica cambios
    python manage.py backfill_guest_users --dry-run # solo muestra qué haría
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from accounts.guest_signup import get_or_create_guest_user
from orders.models import Order


class Command(BaseCommand):
    help = (
        "Vincula pedidos guest (Order.user IS NULL) a un User cliente "
        "auto-creado a partir del email del comprador."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="No escribe; solo lista lo que pasaría.",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]

        orders = Order.objects.filter(user__isnull=True).exclude(email="").order_by("id")
        total = orders.count()
        self.stdout.write(f"Pedidos guest con email a procesar: {total}")
        if total == 0:
            return

        linked = 0
        for order in orders:
            full_name = _extract_full_name(order.notes or "")
            if dry_run:
                self.stdout.write(
                    f"[dry-run] Order #{order.id} email={order.email} "
                    f"nombre='{full_name}'"
                )
                continue
            user = get_or_create_guest_user(
                email=order.email,
                full_name=full_name,
                phone=order.phone or "",
                telegram_username=order.telegram_username or "",
            )
            order.user = user
            order.save(update_fields=["user"])
            linked += 1
            self.stdout.write(
                f"Order #{order.id} email={order.email} -> "
                f"User id={user.id} username={user.username}"
            )
        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f"Vinculados {linked}/{total} pedidos."))


def _extract_full_name(notes: str) -> str:
    """Saca el nombre del comprador de Order.notes.

    El checkout escribe ``"Nombre comprador: {full_name}"`` como notes.
    """
    prefix = "Nombre comprador:"
    for line in notes.splitlines():
        line = line.strip()
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""
