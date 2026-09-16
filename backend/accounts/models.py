import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wechat_openid = models.CharField(max_length=128, null=True, blank=True, unique=True)
    auth_kind = models.CharField(max_length=16, default='system', choices=[('system', '管理账号'), ('dev', '开发模拟'), ('wechat', '微信')])
    nickname = models.CharField(max_length=32, blank=True)
    record_history = models.BooleanField(default=True)
    avatar = models.ForeignKey('assets.Asset', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')

    class Meta:
        verbose_name = '用户'
        verbose_name_plural = verbose_name


class AuthSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_sessions')
    token_digest = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

