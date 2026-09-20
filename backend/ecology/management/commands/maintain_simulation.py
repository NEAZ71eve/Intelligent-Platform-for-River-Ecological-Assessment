import json
from django.core.management.base import BaseCommand, CommandError
from common.audit import audit
from ecology.maintenance import MaintenanceError, create_preview, execute_preview


class Command(BaseCommand):
    help = "预览过期模拟批次清理（默认不删除）。执行必须显式 --execute --token <预览令牌>。"

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--token", help="15 分钟内生成的命令行清理预览令牌；不可重用")
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        if bool(options["execute"]) != bool(options["token"]):
            raise CommandError("执行需要同时提供 --execute 和 --token；默认运行仅生成预览。")
        try:
            result = execute_preview(options["token"]) if options["execute"] else create_preview()
        except MaintenanceError as exc:
            audit("simulation.cleanup.rejected", status="rejected", code=exc.code, source="simulation")
            raise CommandError(str(exc)) from exc
        if options["as_json"]:
            self.stdout.write(json.dumps(result, ensure_ascii=False, default=str))
        elif options["execute"]:
            self.stdout.write(self.style.SUCCESS(f"已清理 {result['batch_count']} 个模拟批次 / {result['observation_count']} 条观测。"))
        else:
            self.stdout.write(f"仅预览：{result['batch_count']} 个候选批次 / {result['observation_count']} 条观测；保留 {len(result['protected'])} 个批次。")
            for row in result["candidates"]:
                self.stdout.write(f"候选 {row['id']} {row['source']}/{row['scenario']} {row['start']} — {row['end']} {row['actual_count']} 条")
            for row in result["protected"]:
                self.stdout.write(f"保护 {row['id']} {'；'.join(row['protection'])}")
            self.stdout.write(f"执行令牌（15 分钟内有效，执行需要显式 --execute --token）：{result['token']}")
