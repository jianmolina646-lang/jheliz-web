from django.urls import path

from . import views

app_name = "support"

urlpatterns = [
    path("", views.ticket_list, name="list"),
    path("nuevo/", views.ticket_create, name="create"),
    path("<int:pk>/", views.ticket_detail, name="detail"),
    path("<int:pk>/mensajes/", views.ticket_messages, name="messages"),
    path("<int:pk>/responder/", views.ticket_reply, name="reply"),
]
