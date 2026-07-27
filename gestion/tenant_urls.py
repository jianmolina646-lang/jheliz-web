"""URLs de la web del inquilino (producto SaaS en jheliztv.xyz)."""
from django.urls import path

from . import tenant_views as v

urlpatterns = [
    # Landing + auth
    path("", v.landing, name="jheliztv_landing"),
    path("registro/", v.register, name="jheliztv_register"),
    path("ingresar/", v.login_view, name="jheliztv_login"),
    path("salir/", v.logout_view, name="jheliztv_logout"),

    # Cobro (Yape)
    path("suscripcion/", v.billing, name="jheliztv_billing"),
    path("suscripcion/pagar/", v.billing_upload, name="jheliztv_billing_upload"),

    # Panel
    path("app/", v.dashboard, name="jheliztv_dashboard"),
    path("app/buscar/", v.search, name="jheliztv_search"),
    path("app/notificaciones.json", v.notifications_json, name="jheliztv_notifications"),
    path("app/telegram/", v.telegram_settings, name="jheliztv_telegram"),
    path("app/telegram/desvincular/", v.telegram_unlink, name="jheliztv_telegram_unlink"),
    path("app/whatsapp/", v.whatsapp_settings, name="jheliztv_whatsapp"),
    path("app/whatsapp/conectar/", v.whatsapp_signup_complete, name="jheliztv_whatsapp_connect"),
    path("app/whatsapp/desvincular/", v.whatsapp_unlink, name="jheliztv_whatsapp_unlink"),
    path("meta/whatsapp/webhook/", v.whatsapp_webhook, name="jheliztv_whatsapp_webhook"),

    # Servicios
    path("app/servicios/", v.services_board, name="jheliztv_services"),
    path("app/servicios/agregar/", v.service_add, name="jheliztv_service_add"),
    path("app/servicios/<int:pk>/", v.service_detail, name="jheliztv_service_detail"),
    path("app/servicios/<int:pk>/editar/", v.service_edit, name="jheliztv_service_edit"),
    path("app/servicios/<int:pk>/eliminar/", v.service_delete, name="jheliztv_service_delete"),

    # Suscripciones
    path("app/suscripciones/agregar/", v.subscription_add, name="jheliztv_subscription_add"),
    path("app/suscripciones/<int:pk>/editar/", v.subscription_edit, name="jheliztv_subscription_edit"),
    path("app/suscripciones/<int:pk>/renovar/", v.subscription_renew, name="jheliztv_subscription_renew"),
    path("app/suscripciones/<int:pk>/eliminar/", v.subscription_delete, name="jheliztv_subscription_delete"),

    # Clientes
    path("app/clientes/", v.clients, name="jheliztv_clients"),
    path("app/clientes/agregar/", v.client_add, name="jheliztv_client_add"),
    path("app/clientes/<int:pk>/editar/", v.client_edit, name="jheliztv_client_edit"),
    path("app/clientes/<int:pk>/eliminar/", v.client_delete, name="jheliztv_client_delete"),
    path("app/clientes/<int:pk>/reporte.pdf", v.client_report_pdf, name="jheliztv_client_report"),

    # Correos en stock (disponibilidad por plataforma)
    path("app/correos/", v.stock_emails, name="jheliztv_emails"),
    path("app/correos/agregar/", v.stock_email_add, name="jheliztv_email_add"),
    path("app/correos/<int:pk>/estado/", v.stock_email_toggle, name="jheliztv_email_toggle"),
    path("app/correos/<int:pk>/editar/", v.stock_email_edit, name="jheliztv_email_edit"),
    path("app/correos/<int:pk>/eliminar/", v.stock_email_delete, name="jheliztv_email_delete"),

    # Movimientos
    path("app/movimientos/agregar/", v.transaction_add, name="jheliztv_transaction_add"),
]
