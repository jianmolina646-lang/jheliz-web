from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permissions import inventory_manager_required
from inventory.models import DigitalAccount

from .forms import SaleForm
from .models import Sale


@login_required
def sale_list(request):
    sales = Sale.objects.select_related("account__service", "created_by")
    return render(request, "sales/list.html", {"sales": sales})


@login_required
def sale_detail(request, pk):
    sale = get_object_or_404(
        Sale.objects.select_related("account__service", "created_by"), pk=pk
    )
    return render(request, "sales/detail.html", {"sale": sale})


@inventory_manager_required
def sale_create(request):
    initial = {}
    if request.method == "GET" and request.GET.get("account", "").isdigit():
        initial["account"] = request.GET["account"]
    form = SaleForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            account = DigitalAccount.objects.select_for_update().get(
                pk=form.cleaned_data["account"].pk
            )
            if account.status != DigitalAccount.Status.AVAILABLE:
                form.add_error("account", "La cuenta ya no está disponible para venta.")
            else:
                sale = form.save(commit=False)
                sale.account = account
                sale.created_by = request.user
                try:
                    sale.full_clean()
                except ValidationError as error:
                    form.add_error(None, error)
                else:
                    sale.save()
                    account.status = DigitalAccount.Status.SOLD
                    account.save(update_fields=("status", "updated_at"))
                    return redirect("sales:detail", pk=sale.pk)
    return render(request, "sales/form.html", {"form": form})
