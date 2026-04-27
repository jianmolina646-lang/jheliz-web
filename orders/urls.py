from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("<uuid:uuid>/", views.order_detail, name="detail"),
]
