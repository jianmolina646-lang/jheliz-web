"""URLs de la web del inquilino (producto SaaS en jheliztv.xyz)."""
from django.urls import path

from . import tenant_views as v

urlpatterns = [
    # Landing + auth
    path("", v.landing, name="jheliztv_landing"),
    path("funciones/", v.features_page, name="jheliztv_features"),
    path("precios/", v.pricing_page, name="jheliztv_pricing"),
    path("como-funciona/", v.how_it_works_page, name="jheliztv_how_it_works"),
    path("preguntas-frecuentes/", v.faq_page, name="jheliztv_faq"),
    path("contacto/", v.contact_page, name="jheliztv_contact"),
    path("registro/", v.register, name="jheliztv_register"),
    path("ingresar/", v.login_view, name="jheliztv_login"),
    path("recuperar/", v.password_recovery, name="jheliztv_password_recovery"),
    path(
        "recuperar/correo/",
        v.TenantPasswordResetView.as_view(),
        name="jheliztv_password_reset",
    ),
    path(
        "recuperar/correo/enviado/",
        v.TenantPasswordResetDoneView.as_view(),
        name="jheliztv_password_reset_done",
    ),
    path(
        "recuperar/correo/<uidb64>/<token>/",
        v.StandardTenantPasswordResetConfirmView.as_view(),
        name="jheliztv_password_reset_confirm",
    ),
    path(
        "recuperar/correo/listo/",
        v.StandardTenantPasswordResetCompleteView.as_view(),
        name="jheliztv_password_reset_complete",
    ),
    path(
        "recuperar/<uidb64>/<token>/",
        v.TenantPasswordResetConfirmView.as_view(),
        name="jheliztv_password_recovery_confirm",
    ),
    path(
        "recuperar/listo/",
        v.TenantPasswordResetCompleteView.as_view(),
        name="jheliztv_password_recovery_complete",
    ),
    path("salir/", v.logout_view, name="jheliztv_logout"),
    path("renovar/<uuid:token>/", v.public_renewal, name="jheliztv_public_renewal"),

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
    path("app/suscripciones/reemplazar-cuenta/", v.account_replace, name="jheliztv_account_replace"),

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
    path("app/correos/<int:pk>/clave.json", v.stock_email_secret, name="jheliztv_email_secret"),

    # Movimientos
    path("app/movimientos/agregar/", v.transaction_add, name="jheliztv_transaction_add"),
    path("app/configuracion/monedas/", v.money_settings, name="jheliztv_money_settings"),
    path("app/soporte/", v.support_inbox, name="jheliztv_support"),
    path("app/soporte/<int:pk>/responder/", v.support_reply, name="jheliztv_support_reply"),
    path("app/soporte/<int:pk>/estado/", v.support_status, name="jheliztv_support_status"),
    path("app/renovaciones/", v.renewals_inbox, name="jheliztv_renewals"),
    path("app/renovaciones/metodos/agregar/", v.payment_method_add, name="jheliztv_payment_method_add"),
    path("app/renovaciones/metodos/<int:pk>/eliminar/", v.payment_method_delete, name="jheliztv_payment_method_delete"),
    path("app/renovaciones/<int:pk>/revisar/", v.renewal_review, name="jheliztv_renewal_review"),
    path("app/renovaciones/<int:pk>/comprobante/", v.renewal_proof, name="jheliztv_renewal_proof"),
]
