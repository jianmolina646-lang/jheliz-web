from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("registro/", views.signup, name="signup"),
    path("ingresar/", views.JhelizLoginView.as_view(), name="login"),
    path("salir/", views.JhelizLogoutView.as_view(), name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("perfil/", views.profile, name="profile"),
]
