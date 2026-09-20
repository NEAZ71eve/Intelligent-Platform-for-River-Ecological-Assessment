import copy
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from assets.models import Asset
from common.audit import audit
from common.exceptions import ServiceError
from recognition.models import QueueControl, RecognitionJob
from .geo import match_water_body, published_water_bodies
from .models import AssessmentJob, RuleSet
from .rules import rules_lock
from .serializers import JobInput, JobSerializer, NearbyInput, WaterBodySerializer


class JobList(generics.ListCreateAPIView):
    serializer_class = JobSerializer

    def get_queryset(self):
        return AssessmentJob.objects.filter(owner=self.request.user, expires_at__gt=timezone.now()).select_related('water_body__place', 'station')

    def create(self, request, *args, **kwargs):
        serializer = JobInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        with transaction.atomic():
            User.objects.select_for_update().get(pk=request.user.pk)
            asset = get_object_or_404(Asset.objects.select_for_update(), pk=values['asset_id'], owner=request.user,
                                      purpose='recognition', expires_at__gt=timezone.now(), original_expires_at__gt=timezone.now())
            existing = AssessmentJob.objects.filter(owner=request.user, asset=asset).first()
            if existing:
                if existing.expires_at <= timezone.now():
                    raise ServiceError('记录已过期，请重新上传图片', 'ASSET_EXPIRED', 409)
                return Response(JobSerializer(existing).data)
            if RecognitionJob.objects.filter(asset=asset).exists():
                raise ServiceError('图片已用于花卉识别，请重新上传用于河道评估', 'ASSET_IN_USE', 409)
            QueueControl.objects.get_or_create(name='recognition')
            QueueControl.objects.select_for_update().get(name='recognition')
            active = RecognitionJob.objects.filter(status__in=['queued', 'running']).count() + AssessmentJob.objects.filter(status__in=['queued', 'running']).count()
            if active >= settings.RECOGNITION_QUEUE_LIMIT:
                raise ServiceError('等待处理的图片较多，请稍后重试', 'QUEUE_FULL', 429)
            water_body = None
            if values.get('water_body_id'):
                water_body = get_object_or_404(published_water_bodies(), pk=values['water_body_id'])
            rules_lock()
            rule = RuleSet.objects.select_for_update().filter(is_active=True).first()
            if rule is None:
                raise ServiceError('图像教学规则暂未启用，请稍后再试', 'RULE_NOT_CONFIGURED', 503)
            job = AssessmentJob.objects.create(
                owner=request.user, asset=asset, water_body=water_body,
                latitude=values.get('latitude'), longitude=values.get('longitude'),
                coordinate_system=values.get('coordinate_system', ''), rule_set=rule,
                rule_snapshot=copy.deepcopy(rule.definition), rule_version=rule.version,
                expires_at=timezone.now() + timedelta(days=settings.RECORD_RETENTION_DAYS))
            audit('assessment.queued', request.user, job.pk)
        return Response(JobSerializer(job).data, status=201)


class JobDetail(generics.RetrieveDestroyAPIView):
    serializer_class = JobSerializer

    def get_queryset(self):
        return AssessmentJob.objects.filter(owner=self.request.user, expires_at__gt=timezone.now()).select_related('water_body__place', 'station')

    def perform_destroy(self, instance):
        with transaction.atomic():
            User.objects.select_for_update().get(pk=self.request.user.pk)
            asset = instance.asset
            instance.delete()
            if asset and not RecognitionJob.objects.filter(asset=asset).exists() and not AssessmentJob.objects.filter(asset=asset).exists():
                asset.delete()


class WaterBodyList(generics.ListAPIView):
    serializer_class = WaterBodySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        from ecology.views import resolve_region
        from ecology.series import single_params
        single_params(self.request.query_params, ('region',))
        queryset = published_water_bodies()
        if self.request.query_params.get('region'):
            queryset = queryset.filter(place__region=resolve_region(self.request))
        return queryset.order_by('place__name', 'pk')


class NearbyWaterBodies(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        # Accept lat/lng aliases for API callers; response never echoes precise location.
        params = request.query_params.copy()
        for short, full in [('lat', 'latitude'), ('lng', 'longitude')]:
            if short in params and full not in params:
                params[full] = params[short]
        serializer = NearbyInput(data=params)
        serializer.is_valid(raise_exception=True)
        return Response({'match': match_water_body(**serializer.validated_data)})
