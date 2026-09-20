import re

from django.db.models import Count, F, Prefetch, Q
from rest_framework import generics
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ecology.models import Place
from ecology.series import single_params
from ecology.views import PublicList, by_identifier, resolve_region

from .models import Content, Route, RouteStop
from .serializers import ContentSerializer, RouteSerializer


CONTENT_FILTERS = ("category", "plant_label", "place", "region", "search")
PLANT_LABEL_NAMES = {
    "daisy": "雏菊类花卉", "dandelion": "蒲公英类花卉", "roses": "蔷薇属花卉",
    "sunflowers": "向日葵类花卉", "tulips": "郁金香类花卉",
}


def public_contents():
    return Content.objects.filter(status="published").select_related("place__region").order_by(
        F("published_at").desc(nulls_last=True), "-created_at", "id",
    )


def filtered_contents(request):
    """One filter contract for articles and their public tag counts."""
    params = request.query_params
    single_params(params, CONTENT_FILTERS)
    queryset = public_contents()
    if category := params.get("category"):
        if category not in dict(Content._meta.get_field("category").choices):
            raise ValidationError({"category": "无效的科普分类。"})
        queryset = queryset.filter(category=category)
    if label := params.get("plant_label"):
        if not re.fullmatch(r"[-a-zA-Z0-9_]{1,50}", label):
            raise ValidationError({"plant_label": "植物标签须为 1 至 50 位字母、数字、短横线或下划线。"})
        queryset = queryset.filter(plant_label=label)
    if place_value := params.get("place"):
        place = by_identifier(Place.objects.filter(is_published=True), place_value).first()
        if place is None:
            raise NotFound("未找到公开地点。")
        queryset = queryset.filter(place=place)
    if params.get("region"):
        region = resolve_region(request)
        # A hidden association is not a global article. Only genuinely unlinked
        # content joins the selected region's published-place content.
        queryset = queryset.filter(Q(place__isnull=True) | Q(place__region=region, place__is_published=True))
    if search := params.get("search", "").strip():
        if len(search) > 100:
            raise ValidationError({"search": "搜索词不能超过 100 个字符。"})
        queryset = queryset.filter(Q(title__icontains=search) | Q(summary__icontains=search))
    return queryset


class ContentList(PublicList):
    serializer_class = ContentSerializer

    def get_queryset(self):
        return filtered_contents(self.request)


class ContentTags(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        queryset = filtered_contents(request).order_by()
        categories = dict(Content._meta.get_field("category").choices)
        category_counts = {
            row["category"]: row["count"]
            for row in queryset.values("category").annotate(count=Count("id"))
        }
        labels = queryset.exclude(plant_label="").values("plant_label").annotate(count=Count("id")).order_by("plant_label")
        return Response({
            "categories": [{"value": key, "name": name, "count": category_counts[key]} for key, name in categories.items() if key in category_counts],
            "plant_labels": [{"value": row["plant_label"], "name": PLANT_LABEL_NAMES.get(row["plant_label"], row["plant_label"]), "count": row["count"]} for row in labels],
            "content_count": sum(category_counts.values()),
        })


class ContentDetail(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    queryset = public_contents()
    serializer_class = ContentSerializer


def public_routes():
    public_stops = RouteStop.objects.filter(place__is_published=True, place__region_id=F("route__region_id")).select_related(
        "place__region", "place__water_body",
    ).order_by("order", "id")
    return Route.objects.filter(published=True).select_related("region").prefetch_related(
        Prefetch("stops", queryset=public_stops, to_attr="public_stops"),
    ).order_by("title", "id")


class RouteList(PublicList):
    serializer_class = RouteSerializer

    def get_queryset(self):
        single_params(self.request.query_params, ("region",))
        queryset = public_routes()
        if self.request.query_params.get("region"):
            queryset = queryset.filter(region=resolve_region(self.request))
        return queryset


class RouteDetail(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    queryset = public_routes()
    serializer_class = RouteSerializer
