from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from weatherdata.models import WeatherLocation, WeatherMonth, WeatherRequest
from weatherdata.services import BEIJING, summary


class Command(BaseCommand):
    help = '预览天气缓存更新；仅 --fetch 才会在预算允许时请求上游，无强制绕过缓存。'

    def add_arguments(self, parser):
        parser.add_argument('--location', required=True)
        parser.add_argument('--fetch', action='store_true')

    def handle(self, *args, **options):
        location = WeatherLocation.objects.filter(slug=options['location'], is_active=True).first()
        if not location:
            raise CommandError('没有找到已启用的天气地点。')
        now = timezone.now()
        month = WeatherMonth.objects.filter(month=now.astimezone(BEIJING).strftime('%Y-%m')).first()
        rolling = WeatherRequest.objects.filter(reserved_at__gte=now-timedelta(days=31)).count()
        self.stdout.write(f'月预占 {month.reserved if month else 0}；近 31 天预占 {rolling}；本部署封顶 {settings.QWEATHER_MONTHLY_LIMIT}。')
        if options['fetch']:
            result = summary(location)
            for kind in ('weather', 'air', 'alerts'):
                self.stdout.write(f'{kind}: {result[kind]["status"]}; {result[kind]["reason"] or "ok"}')
        else:
            self.stdout.write('预览：最多 3 次上游请求，每种服务分别计次；缓存命中、预算/冷却阻断不出站。')
