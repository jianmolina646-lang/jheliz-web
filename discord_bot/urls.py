from django.urls import path

from . import views

app_name = "discord_bot"

urlpatterns = [
    path("interactions/", views.interactions_webhook, name="interactions"),
]
