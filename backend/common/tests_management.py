import json
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from accounts.services import issue_session
from common.audit import audit, audit_admin
from common.models import AuditLog
from common.statistics import SHANGHAI
from ecology.models import Place, Region, SimulationRun, SimulationScenario, DataSource
from knowledge.models import Content, Route, RouteStop
from llm.models import UsageLedger
from recognition.models import ModelVersion, RecognitionJob
from assessments.models import AssessmentJob


class ManagementStatisticsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('statistics-admin', is_staff=True)
        cls.regular = User.objects.create_user('ordinary')
        cls.region = Region.objects.create(name='测试区域', slug='stats-test')
        cls.place = Place.objects.create(region=cls.region, slug='stats-place', name='测试地点', kind='park')
        cls.start = datetime(2030, 4, 2, tzinfo=SHANGHAI)
        cls.end = cls.start + timedelta(days=1)

    def setUp(self):
        self.url = reverse('admin:common_managementstats_data')
        self.params = {'start': '2030-04-02', 'end': '2030-04-03'}

    def grant(self, *perms):
        for perm in perms:
            app, codename = perm.split('.')
            self.staff.user_permissions.add(Permission.objects.get(content_type__app_label=app, codename=codename))
        self.client.force_login(self.staff)

    def test_anonymous_nonstaff_and_bare_staff_cannot_read(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.regular)
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_only_permitted_sections_and_no_cross_dataset_query(self):
        self.grant('knowledge.view_content')
        response = self.client.get(self.url, self.params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()['summary']), {'content'})
        self.assertEqual(self.client.get(self.url, {**self.params, 'dataset': 'users'}).status_code, 403)
        page = self.client.get(reverse('admin:common_managementstats_changelist'), self.params)
        self.assertContains(page, '管理统计与查询')
        self.assertNotContains(page, 'value="users"')
        self.assertContains(self.client.get('/admin/'), '管理统计与查询')

    def test_dedicated_permission_allows_aggregates_but_not_audit_records(self):
        self.grant('common.view_managementstats')
        self.assertEqual(set(self.client.get(self.url).json()['summary']),
                         {'users', 'content', 'places', 'recognition', 'assessment', 'llm', 'simulation'})
        self.assertEqual(self.client.get(reverse('admin:common_auditlog_changelist')).status_code, 403)

    def test_bearer_without_admin_session_does_not_unlock_admin(self):
        self.grant('common.view_managementstats')
        self.client.logout()
        token, _ = issue_session(self.staff)
        self.assertEqual(self.client.get(self.url, HTTP_AUTHORIZATION='Bearer ' + token).status_code, 302)

    def test_beijing_half_open_creation_window_current_publication(self):
        self.grant('common.view_managementstats')
        for i, (when, status) in enumerate([(self.start-timedelta(microseconds=1), 'published'),
                                          (self.start, 'published'), (self.end-timedelta(microseconds=1), 'draft'),
                                          (self.end, 'published')]):
            obj = Content.objects.create(title='正文不能泄漏', slug=f'boundary-{i}', body='PRIVATE-BODY', status=status)
            Content.objects.filter(pk=obj.pk).update(created_at=when)
        result = self.client.get(self.url, self.params).json()
        self.assertEqual(result['window']['interval'], '[start, end)')
        self.assertEqual(result['window']['timezone'], 'Asia/Shanghai')
        row = result['summary']['content']
        self.assertEqual(row['current_total'], 4)
        self.assertEqual(row['created_in_window'], 2)
        self.assertEqual(row['current_published'], 3)
        self.assertEqual(row['window_currently_published'], 1)
        self.assertEqual(row['window_status'], {'published': 1, 'draft': 1})

    def test_llm_retained_ledger_scope_status_and_token_semantics(self):
        self.grant('llm.view_usageledger')
        for scope, state, accounted, reserved, estimated in [
            ('recognition','succeeded',100,400,False), ('recognition','failed',20,400,True),
            ('recognition','queued',0,400,False), ('explore','running',0,500,False),
            ('learn','succeeded',90,400,False)]:
            row = UsageLedger.objects.create(owner=None, request_id=uuid.uuid4(), fingerprint='x', scope=scope,
                                            day=self.start.date(), status=state, reserved_tokens=reserved,
                                            accounted_tokens=accounted, max_output_tokens=600, timeout_seconds=45,
                                            usage_estimated=estimated)
            UsageLedger.objects.filter(pk=row.pk).update(created_at=self.start)
        result = self.client.get(self.url, self.params).json()['summary']['llm']['scopes']
        self.assertEqual(result['recognition'], {'submitted':3, 'succeeded':1, 'failed':1, 'reserved_turns':1,
                                               'accounted_tokens':120,'reserved_tokens':400,'estimated_entries':1})
        self.assertEqual(result['explore']['reserved_tokens'], 500)
        self.assertEqual(result['learn']['succeeded'], 1)
        response = self.client.get(self.url, {**self.params,'dataset':'llm','scope':'recognition','status':'failed'})
        self.assertEqual(response.json()['query']['count'], 1)
        self.assertNotIn('fingerprint', response.json()['query']['rows'][0])
        self.assertNotIn('owner_id', response.json()['query']['rows'][0])

    def test_job_status_and_simulation_recorded_counts(self):
        self.grant('common.view_managementstats')
        for model, state in [(RecognitionJob, 'failed'), (AssessmentJob, 'queued')]:
            obj = model.objects.create(owner=self.regular, status=state, expires_at=self.end)
            model.objects.filter(pk=obj.pk).update(created_at=self.start)
        source = DataSource.objects.create(code='stats-sim', name='模拟', kind='simulation')
        scenario = SimulationScenario.objects.create(code='stats-sim', name='模拟', parameters={})
        run = SimulationRun.objects.create(key='stats-run', scenario=scenario, source=source,
                                           start=self.start, end=self.end, seed=1, status='succeeded', counts=42)
        SimulationRun.objects.filter(pk=run.pk).update(created_at=self.start)
        result = self.client.get(self.url, self.params).json()['summary']
        self.assertEqual(result['recognition']['window_status'], {'failed':1})
        self.assertEqual(result['assessment']['window_status'], {'queued':1})
        self.assertEqual(result['simulation']['window_generated_observations'],42)

    def test_bounded_filtered_queries_omit_private_values(self):
        self.grant('accounts.view_user')
        User.objects.filter(pk=self.regular.pk).update(date_joined=self.start, nickname='PRIVATE-NICKNAME', wechat_openid='PRIVATE-OPENID')
        result = self.client.get(self.url, {**self.params, 'dataset':'users', 'page_size':1})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['query']['count'], 1)
        self.assertEqual(len(result.json()['query']['rows']), 1)
        self.assertNotIn('PRIVATE-', result.content.decode())
        self.assertNotIn('username', result.json()['query']['rows'][0])

    def test_invalid_window_paging_and_filters_rejected(self):
        self.grant('common.view_managementstats')
        for extra in [{'start':'invalid'}, {'end':'2030-04-02'}, {'end':'2032-04-03'}, {'dataset':'arbitrary'},
                      {'dataset':'llm','page_size':'101'}, {'dataset':'llm','page':'0'},
                      {'dataset':'llm','page':'1001'}, {'dataset':'llm','page_size':'oops'},
                      {'dataset':'llm','status':'bogus'}, {'dataset':'users','scope':'learn'},
                      {'dataset':'users','status':'active'}]:
            with self.subTest(extra=extra):
                self.assertEqual(self.client.get(self.url, {**self.params,**extra}).status_code,400)
        self.assertEqual(self.client.post(self.url).status_code, 405)
        html = self.client.get(reverse('admin:common_managementstats_changelist'), {'start':'invalid'})
        self.assertEqual(html.status_code,400)


class AdministrativeAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser('auditor', password='test-password-not-production')
        cls.region = Region.objects.create(slug='audit-test',name='区域')
        cls.place = Place.objects.create(region=cls.region, slug='audit-place', name='地点',kind='park')

    def request(self):
        request = RequestFactory().post('/admin/')
        request.user = self.staff
        return request

    def test_legacy_audit_keeps_safe_details_only(self):
        record = audit('legacy.event', self.staff, 'safe-id', status='ok', count=2, question='PRIVATE', password='SECRET')
        self.assertEqual(record.details, {'status':'ok', 'count':2})
        self.assertEqual(record.model_label, '')

    def test_add_and_change_contain_field_names_never_values(self):
        manager = admin.site._registry[Content]
        obj = Content(title='PRIVATE-TITLE',slug='audit-content',body='PRIVATE-BODY')
        manager.save_model(self.request(),obj,SimpleNamespace(changed_data=['title','body','unknown_prompt','password']),False)
        record = AuditLog.objects.get(event='admin.added')
        self.assertEqual(record.model_label, 'knowledge.content')
        self.assertEqual(record.action, 'add')
        self.assertEqual(record.changed_fields, ['body','title'])
        self.assertNotIn('PRIVATE', json.dumps(record.details))
        obj.title='ANOTHER-PRIVATE-TITLE'
        manager.save_model(self.request(),obj,SimpleNamespace(changed_data=['title']),True)
        self.assertEqual(AuditLog.objects.get(event='admin.changed').changed_fields,['title'])
        self.assertEqual(AuditLog.objects.count(),2)

    def test_audit_and_mutation_rollback_together(self):
        manager=admin.site._registry[Content]
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                manager.save_model(self.request(), Content(title='rollback',slug='rollback',body='x'),
                                   SimpleNamespace(changed_data=['body']),False)
                raise RuntimeError('simulate failed inline validation')
        self.assertFalse(Content.objects.filter(slug='rollback').exists())
        self.assertFalse(AuditLog.objects.exists())
        with patch('common.admin_audit.audit_admin', side_effect=RuntimeError('audit failed')):
            with self.assertRaises(RuntimeError):
                manager.save_model(self.request(), Content(title='rollback',slug='rollback-2',body='x'),
                                   SimpleNamespace(changed_data=['body']),False)
        self.assertFalse(Content.objects.filter(slug='rollback-2').exists())

    def test_bulk_delete_records_ids_only_and_rolls_back(self):
        objects=[Content.objects.create(title='PRIVATE',slug=f'bulk-{i}',body='PRIVATE-BODY') for i in range(2)]
        manager=admin.site._registry[Content]
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                manager.delete_queryset(self.request(),Content.objects.filter(pk__in=[o.pk for o in objects]))
                raise RuntimeError('rollback')
        self.assertEqual(Content.objects.count(),2)
        self.assertEqual(AuditLog.objects.count(),0)
        manager.delete_queryset(self.request(),Content.objects.all())
        self.assertFalse(Content.objects.exists())
        logs=AuditLog.objects.filter(event='admin.bulk_deleted')
        self.assertEqual(set(logs.values_list('target_id',flat=True)), {str(o.pk) for o in objects})
        self.assertEqual(set(logs.values_list('action',flat=True)), {'bulk_delete'})
        self.assertTrue(all(row.details=={} for row in logs))

    def test_deleted_actor_is_null_and_target_id_is_retained(self):
        user=User.objects.create_superuser('self-delete',password='test-only')
        request=self.request();request.user=user
        user_id=str(user.pk)
        admin.site._registry[User].delete_model(request,user)
        row=AuditLog.objects.get(event='admin.deleted')
        self.assertIsNone(row.actor_id)
        self.assertEqual(row.target_id,user_id)
        self.assertEqual(row.model_label,'accounts.user')

    def test_bulk_delete_uses_locked_snapshot_if_filter_membership_changes(self):
        original=Content.objects.create(title='original',slug='delete-original',body='x',status='draft')
        manager=admin.site._registry[Content]
        original_audit=audit_admin
        inserted=[]
        def change_selection(*args,**kwargs):
            if not inserted:
                inserted.append(Content.objects.create(title='later',slug='delete-later',body='private',status='draft'))
                Content.objects.filter(pk=original.pk).update(status='published')
            return original_audit(*args,**kwargs)
        with patch('common.admin_audit.audit_admin',side_effect=change_selection):
            manager.delete_queryset(self.request(),Content.objects.filter(status='draft'))
        self.assertFalse(Content.objects.filter(pk=original.pk).exists())
        self.assertTrue(Content.objects.filter(pk=inserted[0].pk).exists())
        self.assertEqual(AuditLog.objects.get().target_id,str(original.pk))

    def test_group_permission_edit_is_audited_without_permission_values(self):
        group=Group.objects.create(name='staff-viewers')
        perm=Permission.objects.get(content_type__app_label='common',codename='view_managementstats')
        self.client.force_login(self.staff)
        response=self.client.post(reverse('admin:auth_group_change',args=[group.pk]),
                                  {'name':group.name,'permissions':[perm.pk],'_save':'Save'})
        self.assertEqual(response.status_code,302)
        row=AuditLog.objects.get(event='admin.changed')
        self.assertEqual(row.model_label,'auth.group')
        self.assertEqual(row.changed_fields,['permissions'])
        self.assertEqual(row.details,{})
        self.assertTrue(group.permissions.filter(pk=perm.pk).exists())

    def test_inline_create_change_and_delete_audit(self):
        route=Route.objects.create(region=self.region,slug='audit-route',title='路线')
        manager=admin.site._registry[Route]
        formset_class,_=next(manager.get_formsets_with_inlines(self.request(),route))
        base={'stops-TOTAL_FORMS':'1','stops-INITIAL_FORMS':'0','stops-MIN_NUM_FORMS':'0','stops-MAX_NUM_FORMS':'1000',
              'stops-0-place':str(self.place.pk),'stops-0-order':'1','stops-0-note':'PRIVATE-NOTE'}
        formset=formset_class(base,instance=route,prefix='stops')
        self.assertTrue(formset.is_valid(), formset.errors)
        manager.save_formset(self.request(),None,formset,True)
        stop=route.stops.get()
        self.assertEqual(AuditLog.objects.get(event='admin.inline_added').target_id,str(stop.pk))
        update={**base,'stops-INITIAL_FORMS':'1','stops-0-id':str(stop.pk),'stops-0-note':'PRIVATE-CHANGED'}
        formset=formset_class(update,instance=route,prefix='stops');self.assertTrue(formset.is_valid(),formset.errors)
        manager.save_formset(self.request(),None,formset,True)
        self.assertEqual(AuditLog.objects.get(event='admin.inline_changed').changed_fields,['note'])
        formset=formset_class({**update,'stops-0-DELETE':'on'},instance=route,prefix='stops')
        self.assertTrue(formset.is_valid(),formset.errors)
        manager.save_formset(self.request(),None,formset,True)
        self.assertEqual(AuditLog.objects.get(event='admin.inline_deleted').target_id,str(stop.pk))
        self.assertFalse(RouteStop.objects.exists())

    def test_model_bulk_action_logs_once_without_configuration_values(self):
        version=ModelVersion.objects.create(name='test',version='audit',enabled=True)
        manager=admin.site._registry[ModelVersion]
        with patch.object(manager,'message_user'):
            manager.disable_selected(self.request(),ModelVersion.objects.filter(pk=version.pk))
        log=AuditLog.objects.get()
        self.assertEqual(log.event,'model.disabled')
        self.assertEqual(log.model_label,'recognition.modelversion')
        self.assertEqual(log.action,'disable')
        self.assertEqual(log.target_id,str(version.pk))
        self.assertEqual(log.changed_fields,['enabled'])
        self.assertEqual(log.details,{})

    def test_password_change_has_safe_audit_and_invalid_form_does_not(self):
        user=User.objects.create_user('password-test-user')
        self.client.force_login(self.staff)
        url=reverse('admin:auth_user_password_change',args=[user.pk])
        bad=self.client.post(url,{'password1':'x','password2':'different'})
        self.assertEqual(bad.status_code,200)
        self.assertFalse(AuditLog.objects.filter(event='admin.password_changed').exists())
        password='New-Strong-Testing-Password-93762!'
        good=self.client.post(url,{'password1':password,'password2':password,'usable_password':'true'})
        self.assertEqual(good.status_code,302)
        row=AuditLog.objects.get(event='admin.password_changed')
        self.assertEqual(row.target_id,str(user.pk))
        self.assertEqual(row.changed_fields,['password'])
        self.assertEqual(row.details,{})
        user.refresh_from_db();self.assertTrue(user.check_password(password))

    def test_audit_admin_readonly_even_for_superuser(self):
        record=audit_admin('admin.test', self.staff,self.place,action='change',changed_fields=['name'])
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('admin:common_auditlog_changelist')).status_code,200)
        self.assertEqual(self.client.get(reverse('admin:common_auditlog_add')).status_code,403)
        self.assertEqual(self.client.post(reverse('admin:common_auditlog_change',args=[record.pk]), {'event':'changed'}).status_code,403)
        self.assertEqual(self.client.post(reverse('admin:common_auditlog_delete',args=[record.pk])).status_code,403)
        record.refresh_from_db();self.assertEqual(record.event,'admin.test')
