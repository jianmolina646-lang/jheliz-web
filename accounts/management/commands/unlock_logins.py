"""Borra los lockouts de django-axes para que admin/cliente puedan reintentar.

Uso:

    python manage.py unlock_logins                # borra TODOS los lockouts
    python manage.py unlock_logins --user alice   # sólo los que matcheen 'alice'
    python manage.py unlock_logins --ip 1.2.3.4   # sólo los de esa IP

Sin argumentos limpia toda la tabla de intentos fallidos. Útil cuando los
defaults estuvieron muy estrictos y el panel quedó bloqueando a clientes.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Resetea los lockouts de django-axes (intentos fallidos de login)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            dest="username",
            help="Sólo desbloquear el username dado (substring match).",
        )
        parser.add_argument(
            "--ip",
            dest="ip_address",
            help="Sólo desbloquear esta IP.",
        )

    def handle(self, *args, **opts):
        # Importamos acá para no obligar a django-axes en imports de top-level.
        from axes.models import AccessAttempt

        qs = AccessAttempt.objects.all()
        username = opts.get("username")
        ip_address = opts.get("ip_address")
        if username:
            qs = qs.filter(username__icontains=username)
        if ip_address:
            qs = qs.filter(ip_address=ip_address)

        n = qs.count()
        qs.delete()
        self.stdout.write(self.style.SUCCESS(
            f"OK: {n} registro(s) de intentos fallidos eliminados. "
            "Los usuarios afectados ya pueden volver a iniciar sesión."
        ))
