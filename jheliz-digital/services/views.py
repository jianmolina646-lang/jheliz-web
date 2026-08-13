from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from accounts.permissions import inventory_manager_required

from .forms import DigitalServiceForm
from .models import DigitalService


@login_required
def service_list(request):
    return render(request, "services/list.html", {"services": DigitalService.objects.all()})


@inventory_manager_required
def service_create(request):
    form = DigitalServiceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("services:list")
    return render(request, "services/form.html", {"form": form})
