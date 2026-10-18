from django.urls import path
from .whatsapp_bridge import whatsapp_codes
urlpatterns = [path('_internal/codes/whatsapp/', whatsapp_codes)]
