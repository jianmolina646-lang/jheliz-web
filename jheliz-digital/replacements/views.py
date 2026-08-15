from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permissions import inventory_manager_required
from inventory.models import DigitalAccount

from .forms import ReplacementForm
from .models import Replacement


@login_required
def replacement_list(request):
    replacements = Replacement.objects.select_related(
        "original_account__service", "replacement_account__service", "created_by"
    )
    return render(request, "replacements/list.html", {"replacements": replacements})


@login_required
def replacement_detail(request, pk):
    replacement = get_object_or_404(
        Replacement.objects.select_related(
            "original_account__service", "replacement_account__service", "created_by"
        ),
        pk=pk,
    )
    return render(request, "replacements/detail.html", {"replacement": replacement})


@inventory_manager_required
def replacement_create(request):
    initial = {}
    if request.method == "GET" and request.GET.get("account", "").isdigit():
        initial["original_account"] = request.GET["account"]
    form = ReplacementForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        original_id = form.cleaned_data["original_account"].pk
        replacement_id = form.cleaned_data["replacement_account"].pk
        with transaction.atomic():
            locked = {
                account.pk: account
                for account in DigitalAccount.objects.select_for_update()
                .filter(pk__in=(original_id, replacement_id))
                .order_by("pk")
            }
            original = locked[original_id]
            replacement_account = locked[replacement_id]
            error = None
            if original.status != DigitalAccount.Status.SOLD:
                error = ("original_account", "La cuenta anterior ya no está vendida.")
            elif replacement_account.status != DigitalAccount.Status.AVAILABLE:
                error = ("replacement_account", "La cuenta de reposición ya no está disponible.")
            elif original.service_id != replacement_account.service_id:
                error = ("replacement_account", "Las cuentas deben pertenecer al mismo servicio.")
            elif Replacement.objects.filter(original_account=original).exists():
                error = ("original_account", "Esta cuenta ya tiene una reposición registrada.")
            if error:
                form.add_error(*error)
            else:
                replacement = form.save(commit=False)
                replacement.original_account = original
                replacement.replacement_account = replacement_account
                replacement.created_by = request.user
                replacement.save()
                original.status = DigitalAccount.Status.RETIRED
                replacement_account.status = DigitalAccount.Status.SOLD
                original.save(update_fields=("status", "updated_at"))
                replacement_account.save(update_fields=("status", "updated_at"))
                return redirect("replacements:detail", pk=replacement.pk)
    return render(request, "replacements/form.html", {"form": form})
