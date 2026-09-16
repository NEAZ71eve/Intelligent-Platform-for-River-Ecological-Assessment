from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ecology.simulation import generate


class Command(BaseCommand):
    help = "生成可重放的小时模拟数据。需先 seed_demo；数据不会代表真实监测。"

    def add_arguments(self, parser):
        parser.add_argument("--scenario", choices=["normal", "turbidity", "missing"], default="normal")
        parser.add_argument("--start", required=True, help="含时区的 ISO 时间，必须对齐整点")
        parser.add_argument("--hours", type=int, default=48)
        parser.add_argument("--seed", type=int)

    def handle(self, *args, **options):
        try:
            start = parse_datetime(options["start"])
            if not start or timezone.is_naive(start):
                raise CommandError("--start 必须是含时区的 ISO 时间。")
            run, created = generate(options["scenario"], start, options["hours"], options["seed"])
        except (ValueError, ValidationError, ObjectDoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"{'已生成' if created else '已存在，未重复生成'} {run.counts} 条模拟观测；run_id={run.pk}；key={run.key}"))
