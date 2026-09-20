from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import LLMTurn


@receiver(post_delete, sender=LLMTurn)
def release_deleted_queued_turn(sender, instance, **kwargs):
    # Running attempts remain reserved until their worker finishes/lease expires.
    # Deleting private text must not free a still-active upstream concurrency slot.
    from .models import UsageLedger
    from django.utils import timezone
    UsageLedger.objects.filter(pk=instance.ledger_id, status='queued').update(
        status='failed', error_code='SESSION_DELETED', finished_at=timezone.now())
