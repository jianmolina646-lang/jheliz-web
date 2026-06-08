"""URLs de Jheliz Control. Se incluyen bajo /panel-jheliz-2026/jheliz-control/
ANTES del catch-all admin.site.urls."""
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="gestion_dashboard"),
    # Servicios
    path("servicios/", views.services_board, name="gestion_services"),
    path("servicios/agregar/", views.service_add, name="gestion_service_add"),
    path("servicios/<int:pk>/eliminar/", views.service_delete, name="gestion_service_delete"),
    path("servicios/<int:pk>/", views.service_detail, name="gestion_service_detail"),
    # Suscripciones
    path("suscripciones/agregar/", views.subscription_add, name="gestion_subscription_add"),
    path("suscripciones/<int:pk>/editar/", views.subscription_edit, name="gestion_subscription_edit"),
    path("suscripciones/<int:pk>/renovar/", views.subscription_renew, name="gestion_subscription_renew"),
    path("suscripciones/<int:pk>/eliminar/", views.subscription_delete, name="gestion_subscription_delete"),
    # Clientes
    path("clientes/", views.clients, name="gestion_clients"),
    path("clientes/agregar/", views.client_add, name="gestion_client_add"),
    path("clientes/<int:pk>/editar/", views.client_edit, name="gestion_client_edit"),
    path("clientes/<int:pk>/eliminar/", views.client_delete, name="gestion_client_delete"),
    path("clientes/<int:pk>/reporte.pdf", views.client_report_pdf, name="gestion_client_report"),
    # Movimientos
    path("movimientos/agregar/", views.transaction_add, name="gestion_transaction_add"),
    # Buscador + notificaciones
    path("buscar/", views.search, name="gestion_search"),
    path("notificaciones.json", views.notifications_json, name="gestion_notifications"),
]
