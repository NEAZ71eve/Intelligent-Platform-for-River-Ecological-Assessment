import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class TargetRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    place = models.ForeignKey('ecology.Place', on_delete=models.CASCADE, null=True, blank=True)
    content = models.ForeignKey('knowledge.Content', on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(condition=(models.Q(place__isnull=False, content__isnull=True) | models.Q(place__isnull=True, content__isnull=False)), name='%(class)s_exactly_one_target'),
            models.UniqueConstraint(fields=['owner', 'place'], condition=models.Q(place__isnull=False), name='%(class)s_unique_place'),
            models.UniqueConstraint(fields=['owner', 'content'], condition=models.Q(content__isnull=False), name='%(class)s_unique_content'),
        ]


class Favorite(TargetRecord):
    pass


class History(TargetRecord):
    viewed_at = models.DateTimeField(default=timezone.now)


class Visit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    place = models.ForeignKey('ecology.Place', on_delete=models.CASCADE)
    visited_at = models.DateTimeField(auto_now_add=True)
    visited_on = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ['-visited_at']
        constraints = [models.UniqueConstraint(fields=['owner', 'place', 'visited_on'], name='one_self_visit_per_day')]


class Feedback(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    body = models.CharField(max_length=1000)
    status = models.CharField(max_length=20, default='pending', choices=[('pending', '待处理'), ('resolved', '已处理')])
    reply = models.CharField(max_length=1000, blank=True, default='')
    resolved_at = models.DateTimeField(null=True, blank=True, editable=False)
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, editable=False, on_delete=models.SET_NULL, related_name='handled_feedback')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def clean(self):
        super().clean()
        self.reply = self.reply.strip()
        if self.status == 'resolved' and not self.reply:
            raise ValidationError({'reply': '处理完成前请填写答复。'})
