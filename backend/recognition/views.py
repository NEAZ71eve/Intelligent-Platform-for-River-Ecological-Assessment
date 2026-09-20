from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.response import Response
from accounts.models import User
from assets.models import Asset
from assessments.models import AssessmentJob
from common.audit import audit
from common.exceptions import ServiceError
from .models import QueueControl, RecognitionJob
from .serializers import JobInput, JobSerializer


class JobList(generics.ListCreateAPIView):
    serializer_class = JobSerializer

    def get_queryset(self):
        return RecognitionJob.objects.filter(owner=self.request.user, expires_at__gt=timezone.now())

    def create(self, request, *args, **kwargs):
        serializer = JobInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            User.objects.select_for_update().get(pk=request.user.pk)
            asset = get_object_or_404(Asset, pk=serializer.validated_data['asset_id'], owner=request.user, purpose='recognition', expires_at__gt=timezone.now(), original_expires_at__gt=timezone.now())
            existing = RecognitionJob.objects.filter(owner=request.user, asset=asset).first()
            if existing:
                return Response(JobSerializer(existing).data)
            if AssessmentJob.objects.filter(asset=asset).exists():
                raise ServiceError('这张上传图片已用于河道观察，请重新上传后用于花卉识别', 'ASSET_IN_USE', 409)
            QueueControl.objects.get_or_create(name='recognition')
            QueueControl.objects.select_for_update().get(name='recognition')
            active_count = (RecognitionJob.objects.filter(status__in=['queued', 'running']).count()
                            + AssessmentJob.objects.filter(status__in=['queued', 'running']).count())
            if active_count >= settings.RECOGNITION_QUEUE_LIMIT:
                raise ServiceError('等待处理的图片较多，请稍后重试', 'QUEUE_FULL', 429)
            job = RecognitionJob.objects.create(owner=request.user, asset=asset, expires_at=timezone.now() + timedelta(days=settings.RECORD_RETENTION_DAYS))
            audit('recognition.queued', request.user, job.pk)
        return Response(JobSerializer(job).data, status=201)


class JobDetail(generics.RetrieveDestroyAPIView):
    serializer_class = JobSerializer

    def get_queryset(self):
        return RecognitionJob.objects.filter(owner=self.request.user, expires_at__gt=timezone.now())

    def perform_destroy(self, instance):
        asset = instance.asset
        with transaction.atomic():
            instance.delete()
            if asset:
                asset.delete()
