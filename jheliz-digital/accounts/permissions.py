from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def inventory_manager_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.can_manage_inventory:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped
