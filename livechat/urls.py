from django.urls import path

from . import views

app_name = "livechat"

urlpatterns = [
    path("start/", views.start, name="start"),
    path("<str:token>/send/", views.send, name="send"),
    path("<str:token>/poll/", views.poll, name="poll"),
]
