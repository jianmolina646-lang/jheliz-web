"""Re-encripta las credenciales entregadas que aún estén en texto plano.

Uso:
    python manage.py encrypt_credentials             # dry-run
    python manage.py encrypt_credentials --apply     # ejecuta

Es seguro correrlo varias veces: filas ya cifradas se ignoran.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from orders.encryption import encrypt_text
from orders.models import OrderItem


class Command(BaseCommand):
    help = "Cifra delivered_credentials existentes con Fernet (idempotente)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Aplica los cambios. Sin este flag corre en dry-run.",
        )

    def handle(self, *args, **opts):
        apply_changes: bool = opts["apply"]

        # Leemos el valor crudo de la BD saltándonos from_db_value;
        # usamos la conexión para no pasar por el descriptor del field.
        from django.db import connection

        with connection.cursor() as cur:
            cur.execute(
                "SELECT id, delivered_credentials FROM orders_orderitem "
                "WHERE delivered_credentials IS NOT NULL AND delivered_credentials != ''"
            )
            rows = cur.fetchall()

        to_update: list[tuple[int, str]] = []
        already_ok = 0
        for pk, raw in rows:
            if not isinstance(raw, str):
                continue
            if raw.startswith("gAAAAA"):
                already_ok += 1
                continue
            to_update.append((pk, encrypt_text(raw)))

        self.stdout.write(
            f"Filas con credenciales: {len(rows)} | ya cifradas: {already_ok} | "
            f"a cifrar: {len(to_update)}"
        )

        if not to_update:
            return

        if not apply_changes:
            self.stdout.write(self.style.WARNING("Dry-run: no se aplicaron cambios. Usa --apply."))
            return

        with transaction.atomic():
            for pk, ciphertext in to_update:
                OrderItem.objects.filter(pk=pk).update(delivered_credentials=ciphertext)
        self.stdout.write(self.style.SUCCESS(f"Cifradas {len(to_update)} filas."))
