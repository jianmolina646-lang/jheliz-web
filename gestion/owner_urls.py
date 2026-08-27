"""URLs del panel del dueño de jheliztv.xyz. Se montan bajo ``/control/`` en
``config.urls_jheliztv`` (solo en el dominio jheliztv.xyz)."""
from django.urls import path

from . import owner_views as v

urlpatterns = [
    path("", v.control_dashboard, name="jheliztv_control_dashboard"),
    path("usuarios/", v.control_users, name="jheliztv_control_users"),
    path("usuarios/exportar/", v.control_users_export, name="jheliztv_control_users_export"),
    path("usuarios/accion-masiva/", v.control_users_bulk_action, name="jheliztv_control_users_bulk_action"),
    path("usuarios/<int:pk>/", v.control_user_detail, name="jheliztv_control_user_detail"),
    path("demos/", v.control_demos, name="jheliztv_control_demos"),
    path("pagos/", v.control_payments, name="jheliztv_control_payments"),
    path("ingresar/", v.control_login, name="jheliztv_control_login"),
    path("salir/", v.control_logout, name="jheliztv_control_logout"),
    path("2fa/verificar/", v.control_2fa_verify, name="jheliztv_control_2fa_verify"),
    path("2fa/configurar/", v.control_2fa_setup, name="jheliztv_control_2fa_setup"),
    path("demos/generar/", v.control_demo_create, name="jheliztv_control_demo_create"),
    path("pagos/<int:pk>/aprobar/", v.control_payment_approve, name="jheliztv_control_payment_approve"),
    path("pagos/<int:pk>/rechazar/", v.control_payment_reject, name="jheliztv_control_payment_reject"),
    path("pagos/<int:pk>/comprobante/", v.control_payment_proof, name="jheliztv_control_payment_proof"),
    path("inquilinos/<int:pk>/extender/", v.control_tenant_extend, name="jheliztv_control_tenant_extend"),
    path("inquilinos/<int:pk>/bloquear/", v.control_tenant_block, name="jheliztv_control_tenant_block"),
    path("recuperacion/generar/", v.control_password_recovery, name="jheliztv_control_password_recovery"),
    path("inquilinos/<int:pk>/recuperar-clave/", v.control_tenant_password_reset_link, name="jheliztv_control_tenant_password_reset_link"),
]
