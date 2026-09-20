from rest_framework import serializers

from ecology.serializers import PlaceSerializer

from .models import Content, Route, RouteStop


class ContentPlaceSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    slug = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    kind = serializers.CharField(read_only=True)
    region = serializers.UUIDField(source="region_id", read_only=True)
    region_name = serializers.CharField(source="region.name", read_only=True)
    is_demo = serializers.BooleanField(source="region.is_demo", read_only=True)


class ContentSerializer(serializers.ModelSerializer):
    place = serializers.SerializerMethodField()
    place_summary = serializers.SerializerMethodField()

    class Meta:
        model = Content
        fields = ["id", "title", "slug", "body", "summary", "category", "place", "place_summary", "plant_label", "source", "is_demo", "published_at", "updated_at"]

    def get_place(self, obj):
        return str(obj.place_id) if obj.place_id and obj.place.is_published else None

    def get_place_summary(self, obj):
        if obj.place_id and obj.place.is_published:
            return ContentPlaceSerializer(obj.place).data
        return None


class RouteStopSerializer(serializers.ModelSerializer):
    place = PlaceSerializer(read_only=True)

    class Meta:
        model = RouteStop
        fields = ["id", "order", "note", "place"]


class RouteSerializer(serializers.ModelSerializer):
    stops = serializers.SerializerMethodField()
    stop_count = serializers.SerializerMethodField()
    region_name = serializers.CharField(source="region.name", read_only=True)

    class Meta:
        model = Route
        fields = ["id", "slug", "region", "region_name", "title", "description", "source", "is_demo", "stop_count", "stops"]

    @staticmethod
    def public_stops(obj):
        if not hasattr(obj, "public_stops"):
            obj.public_stops = list(obj.stops.filter(place__is_published=True, place__region_id=obj.region_id).select_related("place__region", "place__water_body").order_by("order", "id"))
        return obj.public_stops

    def get_stops(self, obj):
        return RouteStopSerializer(self.public_stops(obj), many=True).data

    def get_stop_count(self, obj):
        return len(self.public_stops(obj))
