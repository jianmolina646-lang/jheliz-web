from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from .models import Order


@login_required
def order_detail(request, uuid):
    order = get_object_or_404(Order, uuid=uuid)
    if order.user_id and order.user_id != request.user.id and not request.user.is_staff:
        raise Http404
    return render(request, "orders/detail.html", {"order": order})
