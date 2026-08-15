from django.urls import path

from . import views

app_name = "sales"
urlpatterns = [
    path("", views.sale_list, name="list"),
    path("nueva/", views.sale_create, name="create"),
    path("<int:pk>/", views.sale_detail, name="detail"),
]
