from django.contrib import admin
from .models import ModelVersion, RecognitionJob


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = ('name', 'version', 'enabled', 'threshold')


@admin.register(RecognitionJob)
class RecognitionJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'owner', 'status', 'error_code', 'created_at', 'duration_ms')
    list_filter = ('status', 'error_code')
    readonly_fields = tuple(f.name for f in RecognitionJob._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

