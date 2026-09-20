from common.admin_audit import AuditAdminMixin
from django.contrib import admin
from django.utils import timezone

from .models import Content, Route, RouteStop


@admin.register(Content)
class ContentAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ["title", "category", "status", "is_demo", "published_at"]
    list_filter = ["status", "category", "is_demo"]
    search_fields = ["title", "summary", "plant_label"]
    autocomplete_fields = ["place"]

    def save_model(self, request, obj, form, change):
        if obj.status == "published" and obj.published_at is None:
            obj.published_at = timezone.now()
        super().save_model(request, obj, form, change)


class RouteStopInline(admin.TabularInline):
    model = RouteStop
    extra = 0
    autocomplete_fields = ["place"]


@admin.register(Route)
class RouteAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ["title", "region", "published", "is_demo"]
    list_filter = ["published", "is_demo", "region"]
    search_fields = ["title"]
    inlines = [RouteStopInline]
