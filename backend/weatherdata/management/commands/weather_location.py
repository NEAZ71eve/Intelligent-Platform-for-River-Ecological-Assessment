from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from weatherdata.models import WeatherLocation


class Command(BaseCommand):
    help = '配置已核对的真实地点（不发送上游请求，不修改模拟区域）。'

    def add_arguments(self, parser):
        parser.add_argument('--slug', required=True)
        parser.add_argument('--name', required=True)
        parser.add_argument('--latitude', required=True)
        parser.add_argument('--longitude', required=True)
        parser.add_argument('--source', required=True, help='坐标核对来源说明')
        parser.add_argument('--scope-note', default='附近约 1 公里网格的气象资料，不代表校园内实测。')
        parser.add_argument('--order', type=int, default=0)
        parser.add_argument('--inactive', action='store_true')

    def handle(self, *args, **options):
        try:
            latitude = Decimal(options['latitude']).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            longitude = Decimal(options['longitude']).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            location, _ = WeatherLocation.objects.update_or_create(slug=options['slug'], defaults={
                'name': options['name'], 'latitude': latitude, 'longitude': longitude,
                'coordinate_source': options['source'], 'scope_note': options['scope_note'],
                'sort_order': options['order'], 'is_active': not options['inactive'],
            })
        except (ValidationError, InvalidOperation, ValueError):
            raise CommandError('地点参数无效；请核对 WGS84 坐标、唯一短名、来源说明与排序。') from None
        self.stdout.write(f'已保存 {location.slug}（坐标按上游精度保留两位小数；未请求天气 API）。')
