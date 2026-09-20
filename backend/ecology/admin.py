from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from common.admin_audit import AuditAdminMixin
from common.audit import audit
from .forms import SimulationCleanupConfirmForm
from .maintenance import MaintenanceError, create_preview, execute_preview

from .models import DataSource, MapLayout, Metric, Observation, Place, Region, SimulationRun, SimulationScenario, Station, WaterBody, SimulationRetentionPolicy, SimulationCleanupPreview


@admin.register(Region)
class RegionAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ["name", "slug", "is_demo"]
    search_fields = ["name", "slug"]


@admin.register(MapLayout)
class MapLayoutAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ["name", "region", "version", "is_active"]
    list_filter = ["region", "is_active"]

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.places.exists():
            fields = ("region", "version", "image_width", "image_height")
            return fields + (("image_url",) if obj.image_url else ())
        return ()


@admin.register(Place)
class PlaceAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ["name", "region", "kind", "map_layout", "is_published"]
    list_filter = ["region", "kind", "is_published"]
    search_fields = ["name", "slug"]
    autocomplete_fields = ["region"]


@admin.register(WaterBody)
class WaterBodyAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ["place"]
    autocomplete_fields = ["place"]


@admin.register(Station)
class StationAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ["name", "code", "kind", "region", "water_body", "is_active"]
    list_filter = ["kind", "region", "is_active"]
    search_fields = ["code", "name"]


@admin.register(Metric)
class MetricAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ["code", "name", "unit", "station_kind", "min_value", "max_value"]
    list_filter = ["station_kind"]
    search_fields = ["code", "name"]


@admin.register(DataSource)
class DataSourceAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ["code", "name", "kind", "is_active"]
    list_filter = ["kind", "is_active"]
    search_fields = ["code", "name"]


@admin.register(Observation)
class ObservationAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ["station", "metric", "value", "unit", "observed_at", "source", "quality_status"]
    list_filter = ["source__kind", "source", "quality_status", "metric"]
    date_hierarchy = "observed_at"
    readonly_fields = ["id", "dedupe_key", "ingested_at", "created_at", "updated_at"]
    autocomplete_fields = ["station", "metric", "source"]

    def has_add_permission(self, request):
        return False  # New observations enter through validated generation/import commands.

    def has_change_permission(self, request, obj=None):
        return False  # Keep historical provenance immutable; correct via a new source/batch.

    def has_delete_permission(self, request, obj=None):
        return False  # Batch cleanup must validate retention and all linked observations.


@admin.register(SimulationScenario)
class SimulationScenarioAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ["code", "name", "seed", "version"]


@admin.register(SimulationRun)
class SimulationRunAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ["id", "scenario", "source", "start", "end", "created_at", "status", "actual_count", "counts", "elapsed_ms", "error_code"]
    list_filter = ["scenario", "source", "status"]
    search_fields = ["=id", "key", "source__code", "scenario__code"]
    date_hierarchy = "created_at"
    change_list_template = "admin/ecology/simulationrun/change_list.html"
    readonly_fields = [field.name for field in SimulationRun._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


    def get_queryset(self, request):
        return super().get_queryset(request).select_related("source", "scenario").annotate(actual_observations=Count("observations"))

    @admin.display(description="实际观测数", ordering="actual_observations")
    def actual_count(self, obj):
        return obj.actual_observations

    def may_maintain(self, request):
        return (request.user.is_active and request.user.is_staff
                and request.user.has_perm("ecology.view_simulationrun")
                and request.user.has_perm("ecology.maintain_simulation"))

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, {**(extra_context or {}), "may_maintain": self.may_maintain(request)})

    def get_urls(self):
        return [path("maintenance/", self.admin_site.admin_view(self.maintenance_view), name="ecology_simulationrun_maintenance")] + super().get_urls()

    def maintenance_view(self, request):
        if not self.may_maintain(request):
            raise PermissionDenied
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        context = {**self.admin_site.each_context(request), "opts": self.model._meta,
                   "title": "模拟批次维护", "plan": None, "form": None}
        if request.method == "POST":
            action = request.POST.get("action")
            try:
                if action == "preview":
                    plan = create_preview(request.user)
                    context.update(plan=plan, form=SimulationCleanupConfirmForm(initial={"token": plan["token"]}))
                elif action == "execute":
                    form = SimulationCleanupConfirmForm(request.POST)
                    if not form.is_valid():
                        raise MaintenanceError("confirmation_required", "请先生成预览，并勾选清理确认。")
                    result = execute_preview(form.cleaned_data["token"], request.user)
                    self.message_user(request, f"已清理 {result['batch_count']} 个过期模拟批次、{result['observation_count']} 条观测。", messages.SUCCESS)
                    return redirect(reverse("admin:ecology_simulationrun_maintenance"))
                else:
                    raise MaintenanceError("invalid_action", "不支持的维护操作。")
            except MaintenanceError as exc:
                audit("simulation.cleanup.rejected", actor=request.user, status="rejected", code=exc.code, source="simulation")
                context["error"] = str(exc)
                return TemplateResponse(request, "admin/ecology/simulationrun/maintenance.html", context, status=400)
        return TemplateResponse(request, "admin/ecology/simulationrun/maintenance.html", context)


@admin.register(SimulationRetentionPolicy)
class SimulationRetentionPolicyAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ["retain_days", "keep_successful", "updated_at"]
    readonly_fields = ["updated_at"]

    def has_add_permission(self, request):
        return not SimulationRetentionPolicy.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SimulationCleanupPreview)
class SimulationCleanupPreviewAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ["id", "actor", "observation_count", "created_at", "expires_at", "consumed_at"]
    list_filter = ["consumed_at", "created_at"]
    search_fields = ["=id"]
    date_hierarchy = "created_at"
    readonly_fields = [field.name for field in SimulationCleanupPreview._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
