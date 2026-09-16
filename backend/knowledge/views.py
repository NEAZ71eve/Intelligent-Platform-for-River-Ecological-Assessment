from django.db.models import Q
from rest_framework import generics
from rest_framework.permissions import AllowAny

from ecology.views import PublicList, resolve_region

from .models import Content, Route
from .serializers import ContentSerializer, RouteSerializer


class ContentList(PublicList):
    serializer_class = ContentSerializer

    def get_queryset(self):
        queryset = Content.objects.filter(status="published")
        if category := self.request.query_params.get("category"):
            queryset = queryset.filter(category=category)
        if label := self.request.query_params.get("plant_label"):
            queryset = queryset.filter(plant_label=label)
        if search := self.request.query_params.get("search"):
            queryset = queryset.filter(Q(title__icontains=search[:100]) | Q(summary__icontains=search[:100]))
        return queryset


class ContentDetail(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    queryset = Content.objects.filter(status="published")
    serializer_class = ContentSerializer


class RouteList(PublicList):
    serializer_class = RouteSerializer

    def get_queryset(self):
        queryset = Route.objects.filter(published=True)
        if self.request.query_params.get("region"):
            queryset = queryset.filter(region=resolve_region(self.request))
        return queryset


class RouteDetail(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    queryset = Route.objects.filter(published=True)
    serializer_class = RouteSerializer
