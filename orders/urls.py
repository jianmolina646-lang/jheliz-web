from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("carrito/", views.cart_view, name="cart"),
    path("carrito/agregar/", views.add_to_cart, name="add_to_cart"),
    path("carrito/quitar/<int:index>/", views.cart_remove, name="cart_remove"),
    path("carrito/vaciar/", views.cart_clear, name="cart_clear"),
    path("checkout/", views.checkout, name="checkout"),
    path("webhooks/mercadopago/", views.mercadopago_webhook, name="mercadopago_webhook"),
    path("<uuid:uuid>/gracias/", views.checkout_return, name="checkout_return"),
    path("<uuid:uuid>/yape/", views.yape_payment, name="yape_payment"),
    path("<uuid:uuid>/", views.order_detail, name="detail"),
]
