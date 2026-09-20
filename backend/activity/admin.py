from common.admin_audit import AuditAdminMixin
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from .models import Favorite, Feedback, History, Visit


@admin.register(Feedback)
class FeedbackAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'owner', 'status', 'created_at', 'resolved_at', 'handled_by')
    list_filter = ('status',)
    readonly_fields = ('owner', 'body', 'created_at', 'resolved_at', 'handled_by')

    def has_add_permission(self, request):
        return False

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if not change or not self.has_change_permission(request, obj):
            raise PermissionDenied('只有具有反馈修改权限的管理员可以处理反馈。')
        previous = Feedback.objects.select_for_update().get(pk=obj.pk)
        obj.full_clean()
        if obj.status == 'resolved':
            if previous.status != 'resolved' or previous.reply != obj.reply or previous.resolved_at is None:
                obj.resolved_at = timezone.now()
                obj.handled_by = request.user
            else:
                obj.resolved_at = previous.resolved_at
                obj.handled_by = previous.handled_by
        else:
            obj.resolved_at = None
            obj.handled_by = None
        super().save_model(request, obj, form, change)


class ActivityAdmin(AuditAdminMixin, admin.ModelAdmin):
    pass


for model in (Favorite, History, Visit):
    admin.site.register(model, ActivityAdmin)
