from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("carrito/", views.cart_view, name="cart"),
    path("carrito/agregar/", views.add_to_cart, name="add_to_cart"),
    path("carrito/quitar/<int:index>/", views.cart_remove, name="cart_remove"),
    path("carrito/vaciar/", views.cart_clear, name="cart_clear"),
    path("carrito/linea/<int:index>/editar/", views.cart_update_line, name="cart_update_line"),
    path("carrito/linea/<int:index>/duplicar/", views.cart_duplicate_line, name="cart_duplicate_line"),
    path("carrito/cupon/aplicar/", views.cart_apply_coupon, name="cart_apply_coupon"),
    path("carrito/cupon/quitar/", views.cart_remove_coupon, name="cart_remove_coupon"),
    path("renovar/<int:item_id>/", views.renew_item, name="renew_item"),
    path("checkout/", views.checkout, name="checkout"),
    path("webhooks/mercadopago/", views.mercadopago_webhook, name="mercadopago_webhook"),
    path("webhooks/telegram/<str:secret>/", views.telegram_webhook, name="telegram_webhook"),
    path("<uuid:uuid>/gracias/", views.checkout_return, name="checkout_return"),
    path("<uuid:uuid>/yape/", views.yape_payment, name="yape_payment"),
    path("<uuid:uuid>/", views.order_detail, name="detail"),
]
