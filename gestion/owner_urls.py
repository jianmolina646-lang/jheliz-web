"""URLs del panel del dueño de jheliztv.xyz. Se montan bajo ``/control/`` en
``config.urls_jheliztv`` (solo en el dominio jheliztv.xyz)."""
from django.urls import path

from . import owner_views as v

urlpatterns = [
    path("", v.control_dashboard, name="jheliztv_control_dashboard"),
    path("ingresar/", v.control_login, name="jheliztv_control_login"),
    path("salir/", v.control_logout, name="jheliztv_control_logout"),
    path("pagos/<int:pk>/aprobar/", v.control_payment_approve, name="jheliztv_control_payment_approve"),
    path("pagos/<int:pk>/rechazar/", v.control_payment_reject, name="jheliztv_control_payment_reject"),
    path("inquilinos/<int:pk>/extender/", v.control_tenant_extend, name="jheliztv_control_tenant_extend"),
]
