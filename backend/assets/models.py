import uuid
from django.conf import settings
from django.db import models


class Asset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='assets')
    purpose = models.CharField(max_length=20, choices=[('avatar', '头像'), ('recognition', '识别')])
    original = models.FileField(upload_to='originals/', blank=True)
    thumbnail = models.FileField(upload_to='thumbnails/', blank=True)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    byte_size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    original_expires_at = models.DateTimeField(db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '私有图片'
        verbose_name_plural = verbose_name

