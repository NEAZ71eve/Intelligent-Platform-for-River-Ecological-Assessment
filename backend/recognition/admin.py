from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from .artifacts import ModelError
from .models import ModelVersion, RecognitionJob
from .registry import activate_model


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = ('name', 'version', 'enabled', 'threshold', 'checksum')
    list_filter = ('enabled',)
    readonly_fields = tuple(field.name for field in ModelVersion._meta.fields)
    actions = ('activate_selected', 'disable_selected')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description='启用所选版本（可回退旧版本）')
    def activate_selected(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, '请只选择一个版本。', messages.ERROR)
            return
        try:
            activate_model(queryset.get().pk, actor=request.user)
        except (ModelError, OSError, ValidationError) as exc:
            self.message_user(request, f'启用失败：{getattr(exc, "code", "MODEL_INVALID")}', messages.ERROR)
        else:
            self.message_user(request, '模型已切换；历史识别保留原版本快照。')

    @admin.action(description='停用所选的当前启用版本')
    def disable_selected(self, request, queryset):
        if queryset.filter(enabled=True).exists():
            activate_model(None, actor=request.user)
            self.message_user(request, '图像识别已停用。')


@admin.register(RecognitionJob)
class RecognitionJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'owner', 'status', 'error_code', 'model_version', 'created_at', 'duration_ms')
    list_filter = ('status', 'error_code')
    readonly_fields = tuple(field.name for field in RecognitionJob._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
