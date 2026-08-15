from django.urls import path

from . import views

app_name = "inventory"
urlpatterns = [
    path("", views.account_list, name="list"),
    path("nueva/", views.account_create, name="create"),
    path("<int:pk>/", views.account_detail, name="detail"),
    path("<int:pk>/editar/", views.account_update, name="update"),
    path("<int:pk>/destacar/", views.account_toggle_featured, name="toggle_featured"),
]
