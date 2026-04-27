from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from orders.models import Order

from .forms import LoginForm, ProfileForm, SignupForm
from .models import Role


def signup(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
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
