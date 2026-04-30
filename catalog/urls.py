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
    path("distribuidor/catalogo/", views.distributor_catalog, name="distributor_catalog"),
    path(
        "distribuidor/items/<int:item_id>/cliente/",
        views.distributor_edit_customer,
        name="distributor_edit_customer",
    ),
    path(
        "distribuidor/items/<int:item_id>/reportar/",
        views.distributor_report_broken,
        name="distributor_report_broken",
    ),
    path("tutoriales/", views.tutorials, name="tutorials"),
    path("terminos/", views.terms, name="terms"),
    path("garantia/", views.warranty, name="warranty"),
    path("preguntas-frecuentes/", seo_views.faq, name="faq"),
    path("estado/", seo_views.status_page, name="status"),
    path("resena/gracias/", views.review_thanks, name="review_thanks"),
    path("resena/<str:token>/", views.submit_review, name="review_submit"),
]
