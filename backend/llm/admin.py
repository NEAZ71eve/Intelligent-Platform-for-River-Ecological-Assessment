from django.conf import settings
from django.contrib import admin
from django.db.models import Count, Sum
from django.utils import timezone

from common.audit import audit
from .models import GatewayConfig, UsageLedger
from .services import ACTIVE, SHANGHAI
from .sources import SCOPE_NAMES


@admin.register(GatewayConfig)
class GatewayConfigAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'enabled', 'environment_enabled', 'key_configured', 'daily_turn_limit', 'updated_at')
    readonly_fields = ('environment_enabled', 'key_configured', 'model_name', 'today_summary', 'updated_at')
    fields = ('enabled', 'environment_enabled', 'key_configured', 'model_name', 'daily_turn_limit',
              'per_user_attempt_limit', 'global_daily_attempt_limit', 'global_daily_token_limit',
              'max_output_tokens', 'timeout_seconds', 'queue_limit', 'max_concurrency', 'today_summary', 'updated_at')

    @admin.display(boolean=True, description='环境总开关')
    def environment_enabled(self, obj):
        return bool(getattr(settings, 'LLM_ENABLED', False))

    @admin.display(boolean=True, description='API Key 已配置（不回显）')
    def key_configured(self, obj):
        return bool(getattr(settings, 'DEEPSEEK_API_KEY', '').strip())

    @admin.display(description='固定调用模型')
    def model_name(self, obj):
        return 'deepseek-flash'

    @admin.display(description='今日用量（北京时间）')
    def today_summary(self, obj):
        entries = UsageLedger.objects.filter(day=timezone.now().astimezone(SHANGHAI).date())
        totals = entries.aggregate(attempts=Count('id'), tokens=Sum('accounted_tokens'))
        reserved = entries.filter(status__in=ACTIVE).aggregate(tokens=Sum('reserved_tokens'))['tokens'] or 0
        success = entries.filter(status='succeeded').count()
        buckets = "；".join(f"{name}成功 {entries.filter(scope=scope, status='succeeded').count()} 次" for scope, name in SCOPE_NAMES.items())
        return f"{buckets}；提交 {totals['attempts']} 次；成功 {success} 次；已结算 {totals['tokens'] or 0} token；待处理预留 {reserved} token"

    def has_add_permission(self, request):
        return not GatewayConfig.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        audit('llm.gateway_changed', request.user, obj.pk, status='enabled' if obj.enabled else 'disabled')


@admin.register(UsageLedger)
class UsageLedgerAdmin(admin.ModelAdmin):
    list_display = ('id', 'scope', 'day', 'status', 'dispatched', 'used_image', 'accounted_tokens', 'usage_estimated', 'duration_ms', 'error_code')
    list_filter = ('scope', 'day', 'status', 'error_code', 'usage_estimated')
    # Private text, image and upstream id are deliberately absent from this model.
    fields = ('id', 'scope', 'day', 'status', 'dispatched', 'used_image', 'reserved_tokens', 'accounted_tokens',
              'usage', 'usage_estimated', 'max_output_tokens', 'timeout_seconds', 'duration_ms', 'error_code',
              'created_at', 'started_at', 'finished_at')
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
