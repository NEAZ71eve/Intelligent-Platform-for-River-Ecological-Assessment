from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import Asset


@receiver(post_delete, sender=Asset)
def remove_asset_files(sender, instance, **kwargs):
    for field in (instance.original, instance.thumbnail):
        if field and field.name:
            storage, name = field.storage, field.name
            transaction.on_commit(lambda storage=storage, name=name: storage.delete(name))

