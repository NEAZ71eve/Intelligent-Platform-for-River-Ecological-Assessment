from django.contrib import admin
from .models import AuditLog, TaskLog


class ReadOnlyLogAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditLog)
class AuditLogAdmin(ReadOnlyLogAdmin):
    list_display = ('event', 'actor', 'target_id', 'created_at')
    list_filter = ('event',)


@admin.register(TaskLog)
class TaskLogAdmin(ReadOnlyLogAdmin):
    list_display = ('task', 'status', 'error_code', 'count', 'duration_ms', 'created_at')
    list_filter = ('task', 'status')

