from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from accounts import password_reset_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "ingresar/",
        auth_views.LoginView.as_view(template_name="accounts/login.html"),
        name="login",
    ),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("recuperar-clave/", password_reset_views.request_code, name="password_reset_request"),
    path("recuperar-clave/verificar/", password_reset_views.verify_code, name="password_reset_verify"),
    path("recuperar-clave/completado/", password_reset_views.complete, name="password_reset_complete"),
    path("servicios/", include("services.urls")),
    path("cuentas/", include("inventory.urls")),
    path("ventas/", include("sales.urls")),
    path("reposiciones/", include("replacements.urls")),
    path("", include("dashboard.urls")),
]
