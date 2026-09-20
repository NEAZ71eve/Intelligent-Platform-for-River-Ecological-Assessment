from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.management.base import BaseCommand, CommandError

from recognition.artifacts import ModelError
from assessments.registry import activate_detector


class Command(BaseCommand):
    help = '启用指定登记版本（可回退旧版本），或 --disable 关闭河道检测。'

    def add_arguments(self, parser):
        parser.add_argument('model_id', nargs='?')
        parser.add_argument('--disable', action='store_true')

    def handle(self, *args, **options):
        if bool(options['model_id']) == bool(options['disable']):
            raise CommandError('请提供模型 UUID，或单独使用 --disable。')
        try:
            model = activate_detector(options['model_id'])
        except (ModelError, ObjectDoesNotExist, ValidationError, OSError) as exc:
            raise CommandError(f'{getattr(exc, "code", "MODEL_ACTIVATION_FAILED")}: {exc}') from exc
        self.stdout.write(self.style.SUCCESS(f'已启用 {model.pk} {model.name}/{model.version}' if model else '河道检测已停用；进行中的任务保持原版本快照。'))
