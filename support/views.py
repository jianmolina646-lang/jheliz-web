from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Ticket


@login_required
def ticket_list(request):
    tickets = request.user.tickets.all()
    return render(request, "support/ticket_list.html", {"tickets": tickets})
