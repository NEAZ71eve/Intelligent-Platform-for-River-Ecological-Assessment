import copy

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from assessments.models import RuleSet
from assessments.rules import RULE_ECOLOGY_V1, RULE_V1, activate_rules, rules_lock

SEEDS = (
    ('image-v1', RULE_V1, '仅漂浮物检测提示；非官方水质或生态指数。'),
    ('ecology-v1', RULE_ECOLOGY_V1, '河道生态评估参考分（优/良/中/差），由河道生态评估 v5 规则迁移；非官方水质或生态指数。'),
)
ACTIVE_DEFAULT = 'ecology-v1'


class Command(BaseCommand):
    help = f'登记可复现规则 image-v1 与 ecology-v1；--activate 在尚无启用规则时激活 {ACTIVE_DEFAULT}，不替换当前版本。'

    def add_arguments(self, parser):
        parser.add_argument('--activate', action='store_true')

    def handle(self, *args, **options):
        created = {}
        with transaction.atomic():
            rules_lock()
            for version, definition, notes in SEEDS:
                rule, is_created = RuleSet.objects.get_or_create(version=version, defaults={
                    'definition': copy.deepcopy(definition), 'notes': notes})
                if rule.definition != definition:
                    raise CommandError(f'{version} 已登记不同规则，请使用新版本，不覆盖历史配置。')
                created[version] = is_created
            activated = options['activate'] and not RuleSet.objects.filter(is_active=True).exists()
            if activated:
                active = RuleSet.objects.get(version=ACTIVE_DEFAULT)
                activate_rules(active.pk)
        parts = [f'{version} {"created" if is_new else "unchanged"}' for version, is_new in created.items()]
        parts.append(f'{ACTIVE_DEFAULT} {"activated" if activated else "not-activated"}')
        self.stdout.write(' '.join(parts))
