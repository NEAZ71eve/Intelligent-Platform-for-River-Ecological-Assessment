from rest_framework import serializers

from .models import DataSource, MapLayout, Metric, Observation, Place, Region, Station


class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ["id", "slug", "name", "description", "is_demo"]


class PlaceSerializer(serializers.ModelSerializer):
    region_name = serializers.CharField(source="region.name", read_only=True)
    is_demo = serializers.BooleanField(source="region.is_demo", read_only=True)
    water_body_id = serializers.UUIDField(source="water_body.id", read_only=True, default=None)

    class Meta:
        model = Place
        fields = ["id", "slug", "name", "kind", "description", "region", "region_name", "is_demo", "map_layout", "x_ratio", "y_ratio", "latitude", "longitude", "coordinate_system", "source_note", "water_body_id"]


class MapSerializer(serializers.ModelSerializer):
    points = serializers.SerializerMethodField()

    class Meta:
        model = MapLayout
        fields = ["id", "region", "name", "version", "image_url", "image_width", "image_height", "attribution", "points"]

    def get_points(self, obj):
        return PlaceSerializer(obj.places.filter(is_published=True).select_related("region", "water_body"), many=True).data


class StationSerializer(serializers.ModelSerializer):
    region_name = serializers.CharField(source="region.name", read_only=True)

    class Meta:
        model = Station
        fields = ["id", "code", "name", "kind", "region", "region_name", "place", "water_body"]


class MetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = Metric
        fields = ["id", "code", "name", "unit", "station_kind", "min_value", "max_value", "description"]


class DataSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataSource
        fields = ["id", "code", "name", "kind", "license", "attribution", "original_url"]


class ObservationSerializer(serializers.ModelSerializer):
    station_id = serializers.UUIDField(read_only=True)
    station_name = serializers.CharField(source="station.name", read_only=True)
    station_code = serializers.CharField(source="station.code", read_only=True)
    metric_code = serializers.CharField(source="metric.code", read_only=True)
    metric_name = serializers.CharField(source="metric.name", read_only=True)
    unit = serializers.CharField(read_only=True)
    source_id = serializers.UUIDField(read_only=True)
    source_name = serializers.CharField(source="source.name", read_only=True)
    source_type = serializers.CharField(source="source.kind", read_only=True)
    is_simulated = serializers.SerializerMethodField()
    simulation_run_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = Observation
        fields = ["id", "station_id", "station_code", "station_name", "metric_code", "metric_name", "value", "unit", "observed_at", "ingested_at", "source_id", "source_name", "source_type", "is_simulated", "quality_status", "simulation_run_id"]

    def get_is_simulated(self, obj):
        return obj.source.kind == DataSource.Kind.SIMULATION


# 河道生态评估任务（AssessmentJob）序列化器与 API 入口
ASSESSMENT_DISCLAIMER = "平台演示评分，非官方水质评价；仅用于课程/毕设演示，不可作为正式水质判定依据。"


class AssessmentJobSerializer(serializers.ModelSerializer):
    """AssessmentJob 详情输出契约。"""

    asset_id = serializers.UUIDField(read_only=True)
    water_body_id = serializers.UUIDField(read_only=True, allow_null=True, default=None)
    station_id = serializers.UUIDField(read_only=True, allow_null=True, default=None)
    rule_set_id = serializers.UUIDField(read_only=True, allow_null=True, default=None)
    model_version_id = serializers.UUIDField(read_only=True, allow_null=True, default=None)
    disclaimer = serializers.SerializerMethodField()

    class Meta:
        model = None  # 延迟绑定，避免在 serializers 模块加载时 ecology.models 尚未导入

        fields = ("id", "asset_id", "status", "error_code", "message",
                  "latitude", "longitude", "coordinate_system",
                  "water_body_id", "station_id",
                  "detections", "score", "grade", "causes",
                  "rule_version", "rule_set_id", "model_version_id",
                  "created_at", "started_at", "finished_at",
                  "duration_ms", "expires_at", "disclaimer")

    def get_disclaimer(self, obj):
        return ASSESSMENT_DISCLAIMER


# 延迟绑定 model：避免循环导入
from .models import AssessmentJob  # noqa: E402
AssessmentJobSerializer.Meta.model = AssessmentJob


class AssessmentJobInput(serializers.Serializer):
    """创建评估任务入参：asset_id + 经纬度（必填）。"""
    asset_id = serializers.UUIDField()
    latitude = serializers.FloatField(required=True)
    longitude = serializers.FloatField(required=True)
    coordinate_system = serializers.ChoiceField(
        required=False, allow_blank=True,
        choices=["", "WGS84", "GCJ02", "BD09"])
