"""Bounded, declarative educational image rules; never a water-quality index."""
import copy
import math

from django.core.exceptions import ValidationError

SCORE_NAME = '图像规则分(教学)'
LIMITATION = '仅反映照片中受支持的漂浮物检测提示，不是官方水质或生态指数，不能据此判断污染成因。'
AREA_NOTE = '检测框并集面积占整张图片的比例，是框面积代理，不是水面覆盖率。'
RULE_V1 = {
    'name': SCORE_NAME,
    'base': 100,
    'floating_debris': {
        'count_steps': [[0, 0], [1, 5], [4, 12], [11, 20]],
        'area_steps': [[0, 0], [0.01, 5], [0.05, 10]],
    },
}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_definition(definition):
    """Only an allowlisted JSON schema; monotone penalties and hard bounds."""
    def invalid():
        raise ValidationError({'definition': '规则须使用受支持的漂浮物计数/框面积档位；阈值、扣分必须有限、递增且处于允许范围。'})

    if not isinstance(definition, dict) or set(definition) != {'name', 'base', 'floating_debris'}:
        invalid()
    if definition['name'] != SCORE_NAME or type(definition['base']) is not int or definition['base'] != 100:
        invalid()
    category = definition['floating_debris']
    if not isinstance(category, dict) or set(category) != {'count_steps', 'area_steps'}:
        invalid()
    for key, bound in (('count_steps', 300), ('area_steps', 1)):
        steps = category[key]
        if not isinstance(steps, list) or not 2 <= len(steps) <= 20 or steps[0] != [0, 0]:
            invalid()
        previous = (-1, -1)
        for step in steps:
            if not isinstance(step, list) or len(step) != 2:
                invalid()
            threshold, penalty = step
            if not _number(threshold) or type(penalty) is not int or not 0 <= threshold <= bound or not 0 <= penalty <= 100:
                invalid()
            if key == 'count_steps' and type(threshold) is not int:
                invalid()
            if threshold <= previous[0] or penalty < previous[1]:
                invalid()
            previous = (threshold, penalty)
        if steps[1][1] < 1:
            invalid()
    return copy.deepcopy(definition)


def rules_lock():
    from recognition.models import QueueControl
    QueueControl.objects.get_or_create(name='assessment_rules')
    return QueueControl.objects.select_for_update().get(name='assessment_rules')


def activate_rules(rule_id=None, actor=None):
    from django.db import transaction
    from common.audit import audit_admin
    from .models import RuleSet
    with transaction.atomic():
        rules_lock()
        rule = RuleSet.objects.select_for_update().get(pk=rule_id) if rule_id else None
        if rule:
            validate_definition(rule.definition)
        previous_id = RuleSet.objects.filter(is_active=True).values_list('pk', flat=True).first()
        RuleSet.objects.filter(is_active=True).update(is_active=False)
        if rule:
            RuleSet.objects.filter(pk=rule.pk).update(is_active=True)
        audit_admin('assessment.rules.activated' if rule else 'assessment.rules.disabled', actor, rule or RuleSet,
                    action='activate' if rule else 'disable', changed_fields=['is_active'],
                    target_id=str(rule.pk) if rule else (str(previous_id) if previous_id else ''))
    return rule


def _step(steps, value):
    return max(penalty for threshold, penalty in steps if value >= threshold)


def union_area(boxes):
    """Exact union of at most 300 axis-aligned boxes, with no overlap double count."""
    xs = sorted({x for box in boxes for x in (box[0], box[2])})
    total = 0.0
    for left, right in zip(xs, xs[1:]):
        intervals = sorted((box[1], box[3]) for box in boxes if box[0] < right and box[2] > left)
        length, end = 0.0, -math.inf
        for bottom, top in intervals:
            length += max(0, top - max(bottom, end))
            end = max(end, top)
        total += (right - left) * length
    return total


def assess(detections, definition, image_width, image_height, *, reason=''):
    rule = validate_definition(definition)
    result = {'score_name': SCORE_NAME, 'score': None, 'grade': '无法确认', 'causes': [], 'issues': {},
              'decision': 'uncertain', 'reason': reason or 'NO_SUPPORTED_DETECTIONS', 'limitation': LIMITATION}
    if reason == 'LOW_IMAGE_QUALITY' or not detections:
        return result
    if not _number(image_width) or not _number(image_height) or image_width <= 0 or image_height <= 0:
        raise ValueError('Invalid image dimensions')
    if not isinstance(detections, list) or len(detections) > 300:
        raise ValueError('Invalid detections')
    boxes = []
    for item in detections:
        if not isinstance(item, dict) or item.get('eval_category') != 'floating_debris':
            raise ValueError('Unsupported detection category')
        box = item.get('bbox')
        if not isinstance(box, list) or len(box) != 4 or not all(_number(value) for value in box):
            raise ValueError('Invalid bounding box')
        if not 0 <= box[0] < box[2] <= image_width or not 0 <= box[1] < box[3] <= image_height:
            raise ValueError('Out-of-bounds bounding box')
        boxes.append(box)
    area = min(1, max(0, union_area(boxes) / (image_width * image_height)))
    penalties = rule['floating_debris']
    score = max(0, min(100, rule['base'] - _step(penalties['count_steps'], len(boxes)) - _step(penalties['area_steps'], area)))
    grade = next(name for minimum, name in [(85, '提示较少'), (70, '需要关注'), (50, '建议核查'), (0, '重点核查')] if score >= minimum)
    result.update(score=score, grade=grade, decision='assessed', reason='',
                  causes=[{'rule': 'floating_debris_observed', 'text': f'图像中有 {len(boxes)} 处疑似漂浮物提示，建议现场核查；无法据图确认污染来源。'}],
                  issues={'floating_debris': {'count': len(boxes), 'box_area_ratio': round(area, 6), 'area_note': AREA_NOTE}})
    return result
