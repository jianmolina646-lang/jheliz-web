from django.urls import path

from . import seo_views, views

app_name = "catalog"

urlpatterns = [
    path("", views.home, name="home"),
    path("productos/", views.product_list, name="products"),
    path("categoria/<slug:slug>/", views.category_detail, name="category"),
    path("producto/<slug:slug>/", views.product_detail, name="product"),
    path("distribuidor/", views.distributor_landing, name="distributor"),
    path("distribuidor/panel/", views.distributor_panel, name="distributor_panel"),
    path("tutoriales/", views.tutorials, name="tutorials"),
    path("terminos/", views.terms, name="terms"),
    path("garantia/", views.warranty, name="warranty"),
    path("preguntas-frecuentes/", seo_views.faq, name="faq"),
    path("estado/", seo_views.status_page, name="status"),
]
