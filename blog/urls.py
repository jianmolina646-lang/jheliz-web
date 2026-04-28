from django.urls import path

from . import feeds, views

app_name = "blog"

urlpatterns = [
    path("", views.post_list, name="list"),
    path("rss/", feeds.LatestPostsFeed(), name="feed"),
    path("categoria/<slug:category_slug>/", views.post_list, name="category"),
    path("<slug:slug>/", views.post_detail, name="detail"),
]
