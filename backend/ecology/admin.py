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


from django.contrib import admin, messages
from django.db import transaction

from common.models import AuditLog
from .models import AssessmentJob, RuleSet


@admin.register(RuleSet)
class RuleSetAdmin(admin.ModelAdmin):
    list_display = ("version", "is_active", "created_at", "notes")
    list_filter = ("is_active",)
    search_fields = ("version", "notes")
    readonly_fields = ("created_at", "updated_at")
    actions = ("activate_selected", "disable_selected")

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="启用所选版本（可回退旧版本）")
    def activate_selected(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "请只选择一个版本。", messages.ERROR)
            return
        target = queryset.get()
        with transaction.atomic():
            RuleSet.objects.filter(is_active=True).update(is_active=False)
            RuleSet.objects.filter(pk=target.pk).update(is_active=True)
            AuditLog.objects.create(event="ruleset.activated", actor=request.user,
                                    target_id=str(target.pk),
                                    details={"version": target.version})
        self.message_user(request, f"已启用 RuleSet {target.version}；历史任务保留原 rule_version。")

    @admin.action(description="停用当前启用版本")
    def disable_selected(self, request, queryset):
        if queryset.filter(is_active=True).exists():
            RuleSet.objects.filter(is_active=True).update(is_active=False)
            AuditLog.objects.create(event="ruleset.disabled", actor=request.user)
            self.message_user(request, "评估规则已停用；后续任务回退到代码内置 RULE_V1。")


@admin.register(AssessmentJob)
class AssessmentJobAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "status", "error_code", "water_body",
                    "grade", "rule_version", "created_at", "duration_ms")
    list_filter = ("status", "error_code", "grade", "water_body")
    search_fields = ("owner__username", "rule_version")
    readonly_fields = tuple(field.name for field in AssessmentJob._meta.fields)
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
