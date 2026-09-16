from django.db import transaction
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.response import Response
from accounts.models import User
from common.exceptions import ServiceError
from .models import Favorite, Feedback, History, Visit
from .serializers import FeedbackSerializer, HistorySerializer, RecordSerializer, TargetInput, VisitSerializer


class RecordsView(generics.ListCreateAPIView):
    model = Favorite
    serializer_class = RecordSerializer

    def get_queryset(self):
        queryset = self.model.objects.filter(owner=self.request.user).select_related('place', 'content')
        for key in ('place_id', 'content_id'):
            if self.request.query_params.get(key):
                value = serializers.UUIDField().run_validation(self.request.query_params[key])
                queryset = queryset.filter(**{key: value})
        return queryset.order_by('-viewed_at' if self.model == History else '-created_at')

    def create(self, request, *args, **kwargs):
        serializer = TargetInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            if self.model == History and not user.record_history:
                raise ServiceError('浏览记录已关闭', 'HISTORY_DISABLED', 409)
            record, created = self.model.objects.get_or_create(owner=user, **serializer.validated_data)
            if self.model == History and not created:
                record.viewed_at = timezone.now()
                record.save(update_fields=['viewed_at'])
        return Response(self.get_serializer(record).data, status=201 if created else 200)


class HistoryView(RecordsView):
    model = History
    serializer_class = HistorySerializer


class RecordDetail(generics.DestroyAPIView):
    model = Favorite
    serializer_class = RecordSerializer

    def get_queryset(self):
        return self.model.objects.filter(owner=self.request.user)


class HistoryDetail(RecordDetail):
    model = History


class VisitsView(generics.ListCreateAPIView):
    serializer_class = VisitSerializer

    def get_queryset(self):
        return Visit.objects.filter(owner=self.request.user).select_related('place')

    def create(self, request, *args, **kwargs):
        serializer = TargetInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        if 'place_id' not in serializer.validated_data:
            raise serializers.ValidationError('游览记录必须选择地点')
        visit, created = Visit.objects.get_or_create(owner=request.user, place_id=serializer.validated_data['place_id'], visited_on=timezone.localdate())
        return Response(VisitSerializer(visit).data, status=201 if created else 200)


class VisitDetail(generics.DestroyAPIView):
    def get_queryset(self):
        return Visit.objects.filter(owner=self.request.user)


class FeedbackView(generics.ListCreateAPIView):
    serializer_class = FeedbackSerializer

    def get_queryset(self):
        return Feedback.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

