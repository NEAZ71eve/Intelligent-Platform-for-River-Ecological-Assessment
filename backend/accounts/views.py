import hashlib
from django.conf import settings
from django.db import transaction
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from common.audit import audit
from common.exceptions import ServiceError
from .models import User
from .serializers import UserSerializer
from .services import exchange_wechat_code, issue_session


class DevInput(serializers.Serializer):
    device_id = serializers.RegexField(r'^[A-Za-z0-9_-]{16,128}$')


class WechatInput(serializers.Serializer):
    code = serializers.CharField(min_length=1, max_length=256)


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'
    kind = 'wechat'

    def post(self, request):
        if self.kind == 'dev':
            # Recheck all three switches at request time as defense in depth.
            if not (settings.ENV == 'development' and settings.DEBUG and settings.ALLOW_DEV_AUTH):
                raise ServiceError('开发模拟登录未启用', 'DEV_AUTH_DISABLED', 404)
            serializer = DevInput(data=request.data)
            serializer.is_valid(raise_exception=True)
            identifier = serializer.validated_data['device_id']
        else:
            serializer = WechatInput(data=request.data)
            serializer.is_valid(raise_exception=True)
            identifier = exchange_wechat_code(serializer.validated_data['code'])
        username = f'{self.kind}_' + hashlib.sha256(identifier.encode()).hexdigest()
        with transaction.atomic():
            user, created = User.objects.get_or_create(username=username, defaults={'auth_kind': self.kind, 'nickname': '生态体验者' if self.kind == 'dev' else '', 'wechat_openid': identifier if self.kind == 'wechat' else None})
            if created:
                user.set_unusable_password()
                user.save(update_fields=['password'])
            if not user.is_active or user.is_staff or user.is_superuser:
                raise ServiceError('此账号不可用于小程序登录', 'ACCOUNT_UNAVAILABLE', 403)
            token, expires = issue_session(user)
            audit('auth.login', user, status=self.kind)
        return Response({'token': token, 'expires_at': expires, 'user': UserSerializer(user, context={'request': request}).data})


class DevLoginView(LoginView):
    kind = 'dev'


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user, context={'request': request}).data)

    @transaction.atomic
    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # Keep the refreshed owner locked through the audit insert as well.
        audit('user.profile_updated', serializer.instance)
        return Response(serializer.data)

    def delete(self, request):
        with transaction.atomic():
            # Serialize with private-record/profile writes before Django collects
            # cascading children; otherwise a newly committed child can be missed.
            try:
                user = User.objects.select_for_update().get(pk=request.user.pk, is_active=True)
            except User.DoesNotExist:
                raise ServiceError('登录已过期，请重新登录', 'AUTH_REQUIRED', 401) from None
            if user.is_staff or user.is_superuser:
                raise ServiceError('管理账号请在管理端处理', 'ACCOUNT_PROTECTED', 403)
            audit('user.deleted', user)
            user.delete()
        return Response(status=204)


class LogoutView(APIView):
    def post(self, request):
        request.auth.delete()
        audit('auth.logout', request.user)
        return Response(status=204)

