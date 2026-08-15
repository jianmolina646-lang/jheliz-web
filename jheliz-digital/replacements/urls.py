from django.urls import path

from . import views

app_name = "replacements"
urlpatterns = [
    path("", views.replacement_list, name="list"),
    path("nueva/", views.replacement_create, name="create"),
    path("<int:pk>/", views.replacement_detail, name="detail"),
]
