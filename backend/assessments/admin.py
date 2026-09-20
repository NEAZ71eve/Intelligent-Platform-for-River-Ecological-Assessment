from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from recognition.artifacts import ModelError
from .models import AssessmentJob, DetectionModel, RuleSet
from .registry import activate_detector
from .rules import activate_rules


@admin.register(DetectionModel)
class DetectionModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'version', 'enabled', 'threshold', 'checksum')
    list_filter = ('enabled',)
    readonly_fields = tuple(field.name for field in DetectionModel._meta.fields)
    actions = ('activate_selected', 'disable_selected')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description='启用所选河道检测版本', permissions=['change'])
    def activate_selected(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, '请只选择一个版本。', messages.ERROR)
            return
        try:
            activate_detector(queryset.get().pk, actor=request.user)
        except (ModelError, OSError, ValidationError) as exc:
            self.message_user(request, f'启用失败：{getattr(exc, "code", "MODEL_INVALID")}', messages.ERROR)
        else:
            self.message_user(request, '河道检测模型已切换，历史任务快照保持原版本。')

    @admin.action(description='停用所选的当前河道检测版本', permissions=['change'])
    def disable_selected(self, request, queryset):
        if queryset.filter(enabled=True).exists():
            activate_detector(None, actor=request.user)
            self.message_user(request, '河道检测模型已停用。')


@admin.register(RuleSet)
class RuleSetAdmin(admin.ModelAdmin):
    list_display = ('version', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active',)
    readonly_fields = ('id', 'created_at', 'updated_at', 'is_active')
    actions = ('activate_selected', 'disable_selected')

    def has_add_permission(self, request):
        return super().has_add_permission(request) and self.has_change_permission(request)

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        return (*fields, 'version', 'definition') if obj and obj.jobs.exists() else fields

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description='启用所选教学规则版本', permissions=['change'])
    def activate_selected(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, '请只选择一个版本。', messages.ERROR)
            return
        try:
            activate_rules(queryset.get().pk, actor=request.user)
        except ValidationError:
            self.message_user(request, '规则格式校验失败。', messages.ERROR)
        else:
            self.message_user(request, '教学规则已切换，已提交任务保留原规则快照。')

    @admin.action(description='停用所选的当前教学规则版本', permissions=['change'])
    def disable_selected(self, request, queryset):
        if queryset.filter(is_active=True).exists():
            activate_rules(None, actor=request.user)
            self.message_user(request, '教学规则已停用。')


@admin.register(AssessmentJob)
class AssessmentJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'owner', 'status', 'decision', 'rule_version', 'model_version', 'created_at')
    list_filter = ('status', 'decision', 'error_code')
    readonly_fields = tuple(field.name for field in AssessmentJob._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
