from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from accounts.models import AuthSession
from assets.models import Asset
from common.models import AuditLog, TaskLog
from recognition.models import RecognitionJob
from assessments.models import AssessmentJob


class Command(BaseCommand):
    help = 'Remove expired originals, private records, sessions and 30-day logs.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        now = timezone.now()
        expired_assets = Asset.objects.filter(expires_at__lte=now)
        originals = Asset.objects.filter(original_expires_at__lte=now).exclude(original='')
        expired_jobs = RecognitionJob.objects.filter(expires_at__lte=now)
        expired_assessments = AssessmentJob.objects.filter(expires_at__lte=now)
        self.stdout.write(f'assets={expired_assets.count()} originals={originals.count()} jobs={expired_jobs.count()} assessments={expired_assessments.count()} dry_run={options["dry_run"]}')
        if options['dry_run']:
            return
        with transaction.atomic():
            for asset in originals:
                storage, name = asset.original.storage, asset.original.name
                Asset.objects.filter(pk=asset.pk).update(original='')
                transaction.on_commit(lambda storage=storage, name=name: storage.delete(name))
            jobs_count, _ = expired_jobs.delete()
            assessments_count, _ = expired_assessments.delete()
            expired_assets.delete()
            AuthSession.objects.filter(expires_at__lte=now).delete()
            cutoff = now - timedelta(days=30)
            AuditLog.objects.filter(created_at__lt=cutoff).delete()
            TaskLog.objects.filter(created_at__lt=cutoff).delete()
            TaskLog.objects.create(task='cleanup_private_data', status='succeeded', count=jobs_count + assessments_count)
