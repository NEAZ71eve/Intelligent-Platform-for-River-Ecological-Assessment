from django.http import FileResponse
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from common.audit import audit
from common.exceptions import ServiceError
from accounts.models import User
from .models import Asset
from .serializers import AssetSerializer, UploadInput
from .services import create_asset


class UploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'upload'

    def post(self, request):
        serializer = UploadInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        asset = create_asset(request.user, serializer.validated_data['file'], serializer.validated_data['purpose'])
        audit('file.uploaded', request.user, asset.pk)
        return Response(AssetSerializer(asset, context={'request': request}).data, status=201)


class AssetDetail(APIView):
    @transaction.atomic
    def delete(self, request, pk):
        try:
            User.objects.select_for_update().get(pk=request.user.pk, is_active=True)
        except User.DoesNotExist:
            raise ServiceError('登录已过期，请重新登录', 'AUTH_REQUIRED', 401) from None
        asset = get_object_or_404(Asset, pk=pk, owner=request.user)
        audit('file.deleted', request.user, asset.pk)
        asset.delete()
        return Response(status=204)


class AssetContent(APIView):
    def get(self, request, pk):
        asset = get_object_or_404(Asset, pk=pk, owner=request.user)
        now = timezone.now()
        variant = request.query_params.get('variant', 'thumbnail')
        if variant not in {'original', 'thumbnail'}:
            raise ServiceError('未知图片版本', 'VALIDATION_ERROR')
        if asset.expires_at is not None and asset.expires_at <= now:
            raise ServiceError('图片已过期', 'FILE_EXPIRED', 410)
        if variant == 'original' and asset.original_expires_at <= now:
            raise ServiceError('识别原图已过期', 'FILE_EXPIRED', 410)
        field = getattr(asset, variant)
        try:
            if not field.name:
                raise FileNotFoundError
            response = FileResponse(field.open('rb'), content_type='image/jpeg')
        except (OSError, ValueError):
            raise ServiceError('图片已清理', 'FILE_NOT_FOUND', 404) from None
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
