import copy
import io

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils import timezone

from accounts.models import User
from .admin import DetectionModelAdmin, RuleSetAdmin
from .models import AssessmentJob, DetectionModel, RuleSet
from .rules import RULE_V1, SCORE_NAME, activate_rules, assess, union_area, validate_definition


def detection(box=None):
    return {'class_id': 9, 'eval_category': 'floating_debris', 'confidence': .9, 'bbox': box or [0, 0, 20, 20]}


class RuleTests(SimpleTestCase):
    def test_no_detections_and_low_quality_do_not_claim_good_water(self):
        for detections, reason in [([], ''), ([detection()], 'LOW_IMAGE_QUALITY')]:
            result = assess(detections, RULE_V1, 100, 100, reason=reason)
            self.assertIsNone(result['score'])
            self.assertEqual(result['decision'], 'uncertain')
            self.assertEqual(result['grade'], '无法确认')
            self.assertEqual(result['score_name'], SCORE_NAME)

    def test_overlapping_boxes_use_union_not_summed_area(self):
        boxes = [[0, 0, 20, 20], [10, 0, 30, 20], [0, 0, 20, 20]]
        self.assertEqual(union_area(boxes), 600)
        result = assess([detection(box) for box in boxes], RULE_V1, 100, 100)
        self.assertEqual(result['issues']['floating_debris']['box_area_ratio'], .06)
        self.assertEqual(result['score'], 85)
        self.assertIn('不是水面覆盖率', result['issues']['floating_debris']['area_note'])
        self.assertEqual(result['decision'], 'assessed')

    def test_unknown_pollution_categories_never_generate_causes(self):
        for category in ['bloom_blackwater', 'outfall_discharge', 'bank_problem', '__import__']:
            item = dict(detection(), eval_category=category)
            with self.subTest(category=category), self.assertRaises(ValueError):
                assess([item], RULE_V1, 100, 100)

    def test_bad_rule_definitions_are_rejected(self):
        candidates = [None, [], {'code': 'eval(1)'}, dict(RULE_V1, base=200), dict(RULE_V1, name='水质指数')]
        for bad_steps in [[[0, 0]], [[0, 0], [1, -1]], [[0, 0], [301, 4]], [[0, 0], [1, 101]],
                          [[0, 0], [1, 5], [2, 4]], [[0, 0], [float('nan'), 4]], [[0, 0], [True, 4]], [[0, 0], [1, 0]]]:
            rule = copy.deepcopy(RULE_V1)
            rule['floating_debris']['count_steps'] = bad_steps
            candidates.append(rule)
        for candidate in candidates:
            with self.subTest(candidate=candidate), self.assertRaises(ValidationError):
                validate_definition(candidate)

    def test_bounding_boxes_are_finite_bounded_and_nonempty(self):
        for box in [[0, 0, 101, 100], [0, 0, 0, 1], [0, 0, float('nan'), 1], [-1, 0, 2, 2]]:
            with self.subTest(box=box), self.assertRaises(ValueError):
                assess([detection(box)], RULE_V1, 100, 100)

    def test_score_is_bounded_and_rule_input_is_not_mutated(self):
        rule = copy.deepcopy(RULE_V1)
        rule['floating_debris']['count_steps'] = [[0, 0], [1, 100]]
        rule['floating_debris']['area_steps'] = [[0, 0], [.001, 100]]
        before = copy.deepcopy(rule)
        self.assertEqual(assess([detection()], rule, 100, 100)['score'], 0)
        self.assertEqual(rule, before)


class RuleRegistryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='rules-user')
        self.rule = RuleSet.objects.create(version='v1', definition=copy.deepcopy(RULE_V1), is_active=True)

    def test_used_rule_and_job_snapshots_are_immutable(self):
        job = AssessmentJob.objects.create(owner=self.user, rule_set=self.rule, rule_version=self.rule.version,
                                            rule_snapshot=copy.deepcopy(self.rule.definition), expires_at=timezone.now())
        self.rule.definition['floating_debris']['count_steps'][1][1] = 6
        with self.assertRaises(ValidationError):
            self.rule.save()
        job.rule_snapshot['floating_debris']['count_steps'][1][1] = 6
        with self.assertRaises(ValidationError):
            job.save()
        job.refresh_from_db()
        self.assertEqual(job.rule_snapshot, RULE_V1)

    def test_single_active_version_and_explicit_switch(self):
        second = RuleSet.objects.create(version='v2', definition=copy.deepcopy(RULE_V1))
        activate_rules(second.pk, actor=self.user)
        self.assertEqual(list(RuleSet.objects.filter(is_active=True).values_list('version', flat=True)), ['v2'])
        activate_rules(None, actor=self.user)
        self.assertFalse(RuleSet.objects.filter(is_active=True).exists())

    def test_view_only_admin_cannot_change_or_activate_rules_or_models(self):
        viewer = User.objects.create_user(username='view-only', is_staff=True)
        viewer.user_permissions.add(*Permission.objects.filter(codename__in=['view_ruleset', 'view_detectionmodel'], content_type__app_label='assessments'))
        request = RequestFactory().get('/admin/')
        request.user = viewer
        for cls, model in [(RuleSetAdmin, RuleSet), (DetectionModelAdmin, DetectionModel)]:
            instance = cls(model, AdminSite())
            self.assertFalse(instance.has_change_permission(request))
            self.assertNotIn('activate_selected', instance.get_actions(request))
            self.assertNotIn('disable_selected', instance.get_actions(request))

    def test_add_permission_alone_cannot_define_rules(self):
        user = User.objects.create_user(username='add-only', is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename='add_ruleset', content_type__app_label='assessments'))
        request = RequestFactory().get('/admin/')
        request.user = user
        self.assertFalse(RuleSetAdmin(RuleSet, AdminSite()).has_add_permission(request))

    def test_seed_is_idempotent_and_requires_explicit_activation(self):
        call_command('seed_assessment_rules', stdout=io.StringIO())
        self.assertTrue(RuleSet.objects.get(pk=self.rule.pk).is_active)
        call_command('seed_assessment_rules', activate=True, stdout=io.StringIO())
        call_command('seed_assessment_rules', activate=True, stdout=io.StringIO())
        self.assertEqual(RuleSet.objects.filter(version='image-v1').count(), 1)
        self.assertTrue(RuleSet.objects.get(pk=self.rule.pk).is_active)
        activate_rules(None)
        call_command('seed_assessment_rules', activate=True, stdout=io.StringIO())
        self.assertTrue(RuleSet.objects.get(version='ecology-v1').is_active)
