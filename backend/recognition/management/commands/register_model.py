from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from recognition.artifacts import ModelError
from recognition.registry import register_model


class Command(BaseCommand):
    help = '校验并登记安全模型目录中的 manifest；同名版本配置不可覆盖。'

    def add_arguments(self, parser):
        parser.add_argument('manifest')
        parser.add_argument('--activate', action='store_true')

    def handle(self, *args, **options):
        try:
            model = register_model(options['manifest'], options['activate'])
        except (ModelError, ValidationError, OSError) as exc:
            raise CommandError(f'{getattr(exc, "code", "MODEL_REGISTRATION_FAILED")}: {exc}') from exc
        self.stdout.write(self.style.SUCCESS(f'{model.pk} {model.name}/{model.version} enabled={model.enabled} checksum={model.checksum}'))
