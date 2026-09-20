"""Bounded staff-only operational counts. These are not traffic analytics."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.apps import apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Sum
from django.utils import timezone

SHANGHAI = ZoneInfo('Asia/Shanghai')
ALL_PERMISSION = 'common.view_managementstats'


@dataclass(frozen=True)
class Dataset:
    label: str
    model_label: str
    time_field: str
    fields: tuple
    status_field: str = ''


DATASETS = {
    'users': Dataset('用户', 'accounts.User', 'date_joined', ('id', 'auth_kind', 'is_active', 'is_staff', 'date_joined')),
    'content': Dataset('科普内容', 'knowledge.Content', 'created_at', ('id', 'title', 'category', 'status', 'is_demo', 'created_at', 'published_at'), 'status'),
    'places': Dataset('地点', 'ecology.Place', 'created_at', ('id', 'name', 'kind', 'is_published', 'created_at')),
    'recognition': Dataset('图像识别任务', 'recognition.RecognitionJob', 'created_at', ('id', 'status', 'error_code', 'duration_ms', 'created_at', 'finished_at'), 'status'),
    'assessment': Dataset('河道评估任务', 'assessments.AssessmentJob', 'created_at', ('id', 'status', 'error_code', 'duration_ms', 'created_at', 'finished_at'), 'status'),
    'llm': Dataset('AI 用量账目', 'llm.UsageLedger', 'created_at', ('id', 'scope', 'day', 'status', 'dispatched', 'accounted_tokens', 'reserved_tokens', 'usage_estimated', 'created_at'), 'status'),
    'simulation': Dataset('模拟批次', 'ecology.SimulationRun', 'created_at', ('id', 'status', 'counts', 'error_code', 'start', 'end', 'created_at'), 'status'),
}


def can_view(user, dataset):
    if not user.is_active or not user.is_staff:
        return False
    model = apps.get_model(dataset.model_label)
    return user.has_perm(ALL_PERMISSION) or user.has_perm(f'{model._meta.app_label}.view_{model._meta.model_name}')


def allowed_datasets(user):
    return {key: item for key, item in DATASETS.items() if can_view(user, item)}


def parse_window(params):
    today = timezone.now().astimezone(SHANGHAI).date()
    try:
        start_text = params.get('start', (today - timedelta(days=6)).isoformat())
        end_text = params.get('end', (today + timedelta(days=1)).isoformat())
        start_day, end_day = date.fromisoformat(start_text), date.fromisoformat(end_text)
        if start_day.isoformat() != start_text or end_day.isoformat() != end_text:
            raise ValueError
    except (TypeError, ValueError):
        raise ValidationError('日期格式必须为 YYYY-MM-DD。')
    if not 0 < (end_day - start_day).days <= 366:
        raise ValidationError('结束日期必须晚于开始日期，单次最多查询 366 天。')
    return (datetime.combine(start_day, time.min, SHANGHAI), datetime.combine(end_day, time.min, SHANGHAI))


def _window(queryset, dataset, window):
    return queryset.filter(**{dataset.time_field + '__gte': window[0], dataset.time_field + '__lt': window[1]})


def state_counts(queryset, field):
    return {item[field]: item['count'] for item in queryset.order_by().values(field).annotate(count=Count('pk'))}


def summary(user, window):
    permitted = allowed_datasets(user)
    if not permitted:
        raise PermissionDenied
    result = {}
    for key, dataset in permitted.items():
        base = apps.get_model(dataset.model_label).objects.all()
        selected = _window(base, dataset, window)
        row = {'label': dataset.label, 'current_total': base.count(), 'created_in_window': selected.count()}
        if dataset.status_field:
            row['window_status'] = state_counts(selected, dataset.status_field)
        if key in {'content', 'places'}:
            publication = {'status': 'published'} if key == 'content' else {'is_published': True}
            row['current_published'] = base.filter(**publication).count()
            row['window_currently_published'] = selected.filter(**publication).count()
        if key == 'llm':
            row['scopes'] = {}
            for scope in ('recognition', 'explore', 'learn'):
                scoped = selected.filter(scope=scope)
                statuses = state_counts(scoped, 'status')
                row['scopes'][scope] = {
                    'submitted': scoped.count(),
                    'succeeded': statuses.get('succeeded', 0),
                    'failed': statuses.get('failed', 0),
                    'reserved_turns': statuses.get('queued', 0) + statuses.get('running', 0),
                    'accounted_tokens': scoped.aggregate(total=Sum('accounted_tokens'))['total'] or 0,
                    'reserved_tokens': scoped.filter(status__in=['queued', 'running']).aggregate(total=Sum('reserved_tokens'))['total'] or 0,
                    'estimated_entries': scoped.filter(usage_estimated=True).count(),
                }
        if key == 'simulation':
            row['window_generated_observations'] = selected.aggregate(total=Sum('counts'))['total'] or 0
            # counts is the recorded generated volume, not a count of remaining rows.
        result[key] = row
    return result


def query_rows(user, params, window):
    key = params.get('dataset', '')
    if not key:
        return None
    dataset = DATASETS.get(key)
    if dataset is None:
        raise ValidationError('不支持的查询数据集。')
    if not can_view(user, dataset):
        raise PermissionDenied
    try:
        page, size = int(params.get('page', '1')), int(params.get('page_size', '20'))
    except (ValueError, TypeError):
        raise ValidationError('页码和每页条数必须为整数。')
    if not 1 <= page <= 1000 or not 1 <= size <= 100:
        raise ValidationError('页码范围为 1–1000，每页最多 100 条。')
    query = _window(apps.get_model(dataset.model_label).objects.all(), dataset, window)
    status = params.get('status', '')
    if status:
        if not dataset.status_field:
            raise ValidationError('此数据集不支持状态筛选。')
        field = query.model._meta.get_field(dataset.status_field)
        if status not in dict(field.choices):
            raise ValidationError('不支持的状态。')
        query = query.filter(**{dataset.status_field: status})
    scope = params.get('scope', '')
    if scope:
        if key != 'llm' or scope not in {'recognition', 'explore', 'learn'}:
            raise ValidationError('板块筛选只支持 AI 用量账目的三个板块。')
        query = query.filter(scope=scope)
    count = query.count()
    rows = list(query.order_by('-' + dataset.time_field, '-pk').values(*dataset.fields)[(page-1)*size:page*size])
    return {'dataset': key, 'label': dataset.label, 'fields': dataset.fields, 'count': count,
            'page': page, 'page_size': size, 'has_next': page * size < count, 'rows': rows}
