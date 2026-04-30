from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from orders.models import Order

from .forms import (
    JhelizPasswordResetForm,
    JhelizSetPasswordForm,
    LoginForm,
    ProfileForm,
    SignupForm,
)
from .models import Role


def signup(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Con AUTHENTICATION_BACKENDS múltiples (axes + ModelBackend),
            # Django requiere indicar qué backend usar al hacer login() de
            # un usuario recién creado.
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            if user.role == Role.DISTRIBUIDOR:
                messages.info(
                    request,
                    "Tu cuenta de distribuidor est\u00e1 pendiente de aprobaci\u00f3n. "
                    "Mientras tanto ver\u00e1s los precios de cliente.",
                )
            return redirect("accounts:dashboard")
    else:
        form = SignupForm()
    return render(request, "accounts/signup.html", {"form": form})


class JhelizLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class JhelizLogoutView(LogoutView):
    next_page = reverse_lazy("catalog:home")


# -- Password reset --------------------------------------------------------
#
# Flujo built-in de Django adaptado al estilo de Jheliz:
#   1. /cuenta/recuperar/             → form con email
#   2. /cuenta/recuperar/enviado/     → "Te enviamos un correo si la cuenta existe"
#   3. /cuenta/recuperar/<uid>/<token>/ → form para nueva contraseña
#   4. /cuenta/recuperar/listo/       → "Contraseña actualizada"
#
# Diseño deliberado: ``PasswordResetView`` siempre responde con éxito aunque
# el email no exista (no enumera cuentas). El correo se envía sólo cuando hay
# match. Token tiene expiración por ``PASSWORD_RESET_TIMEOUT`` en settings
# (default Django: 3 días; usamos 24 h por seguridad).


class JhelizPasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset_form.html"
    email_template_name = "accounts/password_reset_email.txt"
    html_email_template_name = "accounts/password_reset_email.html"
    subject_template_name = "accounts/password_reset_subject.txt"
    form_class = JhelizPasswordResetForm
    success_url = reverse_lazy("accounts:password_reset_done")
    extra_email_context = {"site_name": "Jheliz"}


class JhelizPasswordResetDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class JhelizPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    form_class = JhelizSetPasswordForm
    success_url = reverse_lazy("accounts:password_reset_complete")


class JhelizPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


@login_required
def dashboard(request):
    from datetime import timedelta

    from django.utils import timezone

    from orders.models import OrderItem

    orders = (
        Order.objects.filter(user=request.user)
        .prefetch_related("items__stock_item")
        .order_by("-created_at")[:20]
    )

    now = timezone.now()
    soon = now + timedelta(days=7)
    user_items = OrderItem.objects.filter(order__user=request.user).select_related(
        "order", "plan__product",
    )
    active_items = user_items.filter(
        expires_at__gt=now, order__status=Order.Status.DELIVERED,
    ).order_by("expires_at")
    expiring_soon = active_items.filter(expires_at__lte=soon)
    delivered_count = user_items.filter(order__status=Order.Status.DELIVERED).count()
    # Items con credenciales reemplazadas en los últimos 30 días — para que
    # el cliente/distribuidor vea que migramos su cuenta y use los datos nuevos.
    recently_replaced_window = now - timedelta(days=30)
    recently_replaced = (
        user_items.filter(
            credentials_replaced_at__gte=recently_replaced_window,
            order__status=Order.Status.DELIVERED,
        )
        .select_related("order", "plan__product")
        .order_by("-credentials_replaced_at")[:10]
    )

    stats = {
        "active": active_items.count(),
        "expiring_soon": expiring_soon.count(),
        "delivered": delivered_count,
        "total_orders": Order.objects.filter(user=request.user).count(),
    }

    return render(
        request,
        "accounts/dashboard.html",
        {
            "orders": orders,
            "active_items": active_items[:8],
            "expiring_soon": expiring_soon[:5],
            "recently_replaced": recently_replaced,
            "stats": stats,
        },
    )


@login_required
def profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Datos actualizados.")
            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "accounts/profile.html", {"form": form})
