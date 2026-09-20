"""Server-owned public source references, shared by admission, reads and workers."""
from django.db.models import Q
from ecology.models import Place, Region, WaterBody
from knowledge.models import Content, Route

SCOPE_NAMES = {'recognition': 'AI 识别', 'explore': '生态导览', 'learn': '科普智游'}
SOURCE_FIELDS = {'region': 'region', 'place': 'place', 'water': 'water_body', 'content': 'content', 'route': 'route'}
ALLOWED_SOURCES = {'explore': {'region', 'place', 'water'}, 'learn': {'region', 'content', 'route'}}


def reference(session):
    if session.recognition_job_id:
        return 'recognition_job', session.recognition_job_id
    if session.assessment_job_id:
        return 'assessment_job', session.assessment_job_id
    for source_type, field in SOURCE_FIELDS.items():
        source_id = getattr(session, field + '_id')
        if source_id:
            return source_type, source_id
    return None, None


def public_queryset(source_type):
    if source_type == 'region':
        return Region.objects.all()
    if source_type == 'place':
        return Place.objects.filter(is_published=True).select_related('region')
    if source_type == 'water':
        return WaterBody.objects.filter(place__is_published=True, place__kind__in=['river', 'lake']).select_related('place__region')
    if source_type == 'content':
        return Content.objects.filter(status='published').select_related('place__region')
    if source_type == 'route':
        return Route.objects.filter(published=True).select_related('region')
    raise ValueError('Unknown public source type')


def public_source(session):
    source_type, source_id = reference(session)
    if source_type not in ALLOWED_SOURCES.get(session.scope, set()):
        return None
    return public_queryset(source_type).filter(pk=source_id).first()


def visible_sources_filter():
    recognition = Q(scope='recognition') & (Q(recognition_job__status='succeeded') | Q(assessment_job__status='succeeded'))
    explore = Q(scope='explore') & (Q(region__isnull=False) | Q(place__is_published=True) |
        Q(water_body__place__is_published=True, water_body__place__kind__in=['river', 'lake']))
    learn = Q(scope='learn') & (Q(region__isnull=False) | Q(content__status='published') | Q(route__published=True))
    return recognition | explore | learn
