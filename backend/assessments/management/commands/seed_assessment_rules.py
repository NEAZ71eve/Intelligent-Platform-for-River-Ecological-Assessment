import copy

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from assessments.models import RuleSet
from assessments.rules import RULE_V1, activate_rules, rules_lock


class Command(BaseCommand):
    help = '登记可复现的图像规则分(教学) image-v1；--activate 在尚无启用规则时初始化，不替换当前版本。'

    def add_arguments(self, parser):
        parser.add_argument('--activate', action='store_true')

    def handle(self, *args, **options):
        with transaction.atomic():
            rules_lock()
            rule, created = RuleSet.objects.get_or_create(version='image-v1', defaults={
                'definition': copy.deepcopy(RULE_V1), 'notes': '仅漂浮物检测提示；非官方水质或生态指数。'})
            if rule.definition != RULE_V1:
                raise CommandError('image-v1 已登记不同规则，请使用新版本，不覆盖历史配置。')
            activated = options['activate'] and not RuleSet.objects.filter(is_active=True).exists()
            if activated:
                activate_rules(rule.pk)
        self.stdout.write(f'image-v1 {"created" if created else "unchanged"}{" activated" if activated else ""}')
