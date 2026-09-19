"""Publish original observation notes linked to the five prototype labels."""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from knowledge.models import Content


NOTES = [
    ("daisy", "雏菊类：先观察花的正面", "记录花朵中心与外围的颜色、形状，以及花朵大小。",
     "给同一朵花分别拍摄正面和侧面，再补拍叶片与整株。观察中心和外围是否呈现不同的结构，比较不同角度下的形状。不要只凭白色花瓣或黄色中心判断类别：相似外观可能出现在不同植物中。"),
    ("dandelion", "蒲公英类：记录不同生长阶段", "把花、叶片和果实阶段分别记录，避免只看一处特征。",
     "观察时记录日期、光照和周边环境，分别拍摄花朵、基部叶片与整株。遇到球状绒毛结构时，可以记录其形态，但不要仅凭这一处外观确认植物名称。若只拍摄单片叶子，当前模型可能难以判断。"),
    ("roses", "蔷薇属花卉：观察花瓣和叶片", "对比花瓣排列、叶片边缘和植株整体形态。",
     "从花朵正面与侧面观察花瓣的层次，再记录叶片边缘、排列方式与植株整体形态。拍照时保留自然颜色，避免滤镜改变细节。这里的 roses 是训练数据的宽泛标签，不区分玫瑰、月季等具体种类或园艺品种。"),
    ("sunflowers", "向日葵类：保留花序与整株信息", "同时观察花朵中心、外围和植株的比例关系。",
     "在不踩踏绿地的前提下，先拍摄完整植株，再靠近拍摄花朵的中心与外围。记录叶片形状和花朵朝向，但不要以某一次拍摄的朝向单独判断名称。近距离特写与远景包含的信息不同，可以分别保存在自己的观察笔记中。"),
    ("tulips", "郁金香类：比较侧面轮廓", "比较花朵轮廓、开放程度与叶片形态。",
     "拍摄花朵侧面和正面，记录花朵是否完全开放，再补拍叶片与整株。光照、开放程度和拍摄角度都会改变照片中的外观；颜色相同也不意味着类别相同。尽量让单朵主要花卉位于画面中央，保留完整边缘。"),
]

BOUNDARY = (
    "\n\n识别范围：首版模型只比较 flower_photos 数据集中的五类花卉，"
    "这些标签不是严格的物种级鉴定。模型分数不等于结果正确的概率；"
    "未知植物也可能得到高分，分数未达到所用模型的阈值时会显示无法确认。"
    "当前 v1 模型阈值为 0，未启用按低分拒识；结果仅供候选参考。"
    "本功能不判断食用、药用或接触安全。请勿采摘或食用未知植物。"
    "\n\n观察建议：不采摘、不踩踏、不干扰生境；优先在自然光下拍摄清晰的单一主体。"
    "如结果与实物明显不符，请保留观察记录并重新拍摄其他角度。"
    "\n\n内容说明：HYHQ 原创观察学习稿，未声明这些花卉实际分布在示范校园。"
)


class Command(BaseCommand):
    help = "幂等发布五类花卉观察稿，关联识别标签；保留已有管理员修改。"

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        corrected = 0
        legacy_boundary = BOUNDARY.replace(
            "未知植物也可能得到高分，分数未达到所用模型的阈值时会显示无法确认。"
            "当前 v1 模型阈值为 0，未启用按低分拒识；结果仅供候选参考。",
            "未知植物也可能得到高分，低分会显示无法确认。",
        )
        for label, title, summary, body in NOTES:
            article, is_new = Content.objects.get_or_create(
                slug=f"flower-{label}",
                defaults={
                    "title": title, "summary": summary, "body": body + BOUNDARY,
                    "category": "plants", "plant_label": label,
                    "status": "published", "is_demo": True,
                    "published_at": timezone.now(),
                    "source": "HYHQ 原创观察稿；类别来源：https://www.tensorflow.org/tutorials/load_data/images",
                },
            )
            if article.plant_label != label:
                raise CommandError(f"{article.slug} 已存在且标签不同，停止写入；请管理员核对。")
            # Correct only the exact original seeded copy, preserving administrator edits.
            if not is_new:
                corrected += Content.objects.filter(
                    pk=article.pk, title=title, body=body + legacy_boundary,
                    source="HYHQ 原创观察稿；类别来源：https://www.tensorflow.org/tutorials/load_data/images",
                ).update(body=body + BOUNDARY, updated_at=timezone.now())
            created += is_new
        self.stdout.write(self.style.SUCCESS(f"新增 {created} 篇，订正原始示范稿 {corrected} 篇；管理员修改保持不变。"))
