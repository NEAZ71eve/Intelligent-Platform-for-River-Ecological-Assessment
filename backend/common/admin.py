from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.template.response import TemplateResponse
from django.urls import path

from .models import AuditLog, TaskLog, ManagementStats
from .statistics import allowed_datasets, parse_window, query_rows, summary


class ReadOnlyLogAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditLog)
class AuditLogAdmin(ReadOnlyLogAdmin):
    list_display = ('event', 'action', 'model_label', 'actor', 'target_id', 'created_at')
    list_filter = ('created_at', 'event', 'action', 'model_label')
    search_fields = ('event', 'target_id', 'actor__username', 'model_label')
    date_hierarchy = 'created_at'
    list_select_related = ('actor',)
    readonly_fields = ('id', 'event', 'action', 'model_label', 'target_id', 'actor', 'changed_fields', 'details', 'created_at')


@admin.register(TaskLog)
class TaskLogAdmin(ReadOnlyLogAdmin):
    list_display = ('task', 'status', 'error_code', 'count', 'duration_ms', 'created_at')
    list_filter = ('task', 'status')


@admin.register(ManagementStats)
class ManagementStatsAdmin(ReadOnlyLogAdmin):
    def has_view_permission(self, request, obj=None):
        return bool(allowed_datasets(request.user))

    def has_module_permission(self, request):
        return self.has_view_permission(request)

    def get_urls(self):
        return [path('data/', self.admin_site.admin_view(self.data_view), name='common_managementstats_data'),
                path('', self.admin_site.admin_view(self.changelist_view), name='common_managementstats_changelist')]

    def _payload(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied
        window = parse_window(request.GET)
        return {'window': {'start': window[0].isoformat(), 'end': window[1].isoformat(),
                           'timezone': 'Asia/Shanghai', 'interval': '[start, end)', 'basis': 'created_at (users: date_joined)'},
                'summary': summary(request.user, window),
                'query': query_rows(request.user, request.GET, window)}

    def data_view(self, request):
        if request.method != 'GET':
            return JsonResponse({'error': '只支持 GET。'}, status=405)
        try:
            return JsonResponse(self._payload(request))
        except ValidationError as exc:
            return JsonResponse({'error': '；'.join(exc.messages)}, status=400)

    def changelist_view(self, request, extra_context=None):
        if request.method != 'GET':
            return JsonResponse({'error': '只支持 GET。'}, status=405)
        error, payload = '', None
        try:
            payload = self._payload(request)
        except ValidationError as exc:
            error = '；'.join(exc.messages)
        query = payload['query'] if payload else None
        rows = [[row.get(field) for field in query['fields']] for row in query['rows']] if query else []
        context = {**self.admin_site.each_context(request), 'opts': self.model._meta,
                   'title': '管理统计与查询', 'payload': payload, 'error': error,
                   'query_rows': rows, 'datasets': allowed_datasets(request.user),
                   'start': request.GET.get('start', payload['window']['start'][:10] if payload else ''),
                   'end': request.GET.get('end', payload['window']['end'][:10] if payload else ''),
                   'selected_dataset': request.GET.get('dataset', ''),
                   'selected_status': request.GET.get('status', ''), 'selected_scope': request.GET.get('scope', ''),
                   'page_size': request.GET.get('page_size', '20')}
        if query:
            params = request.GET.copy()
            params['page'] = query['page'] + 1
            context['next_url'] = '?' + params.urlencode()
            params['page'] = max(1, query['page'] - 1)
            context['previous_url'] = '?' + params.urlencode()
        return TemplateResponse(request, 'admin/common/management_stats.html', context, status=400 if error else 200)
