from django.contrib import admin

from .models import DataSource, MapLayout, Metric, Observation, Place, Region, SimulationRun, SimulationScenario, Station, WaterBody


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_demo"]
    search_fields = ["name", "slug"]


@admin.register(MapLayout)
class MapLayoutAdmin(admin.ModelAdmin):
    list_display = ["name", "region", "version", "is_active"]
    list_filter = ["region", "is_active"]

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.places.exists():
            fields = ("region", "version", "image_width", "image_height")
            return fields + (("image_url",) if obj.image_url else ())
        return ()


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ["name", "region", "kind", "map_layout", "is_published"]
    list_filter = ["region", "kind", "is_published"]
    search_fields = ["name", "slug"]
    autocomplete_fields = ["region"]


@admin.register(WaterBody)
class WaterBodyAdmin(admin.ModelAdmin):
    list_display = ["place"]
    autocomplete_fields = ["place"]


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "kind", "region", "water_body", "is_active"]
    list_filter = ["kind", "region", "is_active"]
    search_fields = ["code", "name"]


@admin.register(Metric)
class MetricAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "unit", "station_kind", "min_value", "max_value"]
    list_filter = ["station_kind"]
    search_fields = ["code", "name"]


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "kind", "is_active"]
    list_filter = ["kind", "is_active"]
    search_fields = ["code", "name"]


@admin.register(Observation)
class ObservationAdmin(admin.ModelAdmin):
    list_display = ["station", "metric", "value", "unit", "observed_at", "source", "quality_status"]
    list_filter = ["source__kind", "source", "quality_status", "metric"]
    date_hierarchy = "observed_at"
    readonly_fields = ["id", "dedupe_key", "ingested_at", "created_at", "updated_at"]
    autocomplete_fields = ["station", "metric", "source"]

    def has_add_permission(self, request):
        return False  # New observations enter through validated generation/import commands.

    def has_change_permission(self, request, obj=None):
        return False  # Keep historical provenance immutable; correct via a new source/batch.


@admin.register(SimulationScenario)
class SimulationScenarioAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "seed", "version"]


@admin.register(SimulationRun)
class SimulationRunAdmin(admin.ModelAdmin):
    list_display = ["scenario", "start", "end", "status", "counts", "elapsed_ms", "error_code"]
    list_filter = ["scenario", "status"]
    readonly_fields = [field.name for field in SimulationRun._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
