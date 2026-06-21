from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("registro/", views.signup, name="signup"),
    path("ingresar/", views.JhelizLoginView.as_view(), name="login"),
    path("salir/", views.JhelizLogoutView.as_view(), name="logout"),
    # Password reset (flujo built-in de Django con templates de VirtualidadSP).
    path(
        "recuperar/",
        views.JhelizPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "recuperar/enviado/",
        views.JhelizPasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "recuperar/<uidb64>/<token>/",
        views.JhelizPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "recuperar/listo/",
        views.JhelizPasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("", views.dashboard, name="dashboard"),
    path("perfil/", views.profile, name="profile"),
    # Web Push (PWA notifications)
    path("push/config/", views.push_config, name="push_config"),
    path("push/subscribe/", views.push_subscribe, name="push_subscribe"),
    path("push/unsubscribe/", views.push_unsubscribe, name="push_unsubscribe"),
    # Wallet (saldo de distribuidor)
    path("wallet/", views.wallet, name="wallet"),
    path("wallet/recargar/", views.wallet_recharge, name="wallet_recharge"),
    path("wallet/movimientos/", views.wallet_history, name="wallet_history"),
]
