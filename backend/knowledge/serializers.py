from rest_framework import serializers

from ecology.serializers import PlaceSerializer

from .models import Content, Route, RouteStop


class ContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Content
        fields = ["id", "title", "slug", "body", "summary", "category", "place", "plant_label", "source", "is_demo", "published_at", "updated_at"]


class RouteStopSerializer(serializers.ModelSerializer):
    place = PlaceSerializer(read_only=True)

    class Meta:
        model = RouteStop
        fields = ["id", "order", "note", "place"]


class RouteSerializer(serializers.ModelSerializer):
    stops = serializers.SerializerMethodField()

    class Meta:
        model = Route
        fields = ["id", "slug", "region", "title", "description", "source", "is_demo", "stops"]

    def get_stops(self, obj):
        return RouteStopSerializer(obj.stops.filter(place__is_published=True).select_related("place__region", "place__water_body"), many=True).data
