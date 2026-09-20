from django.urls import path

from . import views

urlpatterns = [
    path("content-tags/", views.ContentTags.as_view(), name="content-tags"),
    path("contents/", views.ContentList.as_view(), name="content-list"),
    path("contents/<uuid:pk>/", views.ContentDetail.as_view(), name="content-detail"),
    path("routes/", views.RouteList.as_view(), name="route-list"),
    path("routes/<uuid:pk>/", views.RouteDetail.as_view(), name="route-detail"),
]
