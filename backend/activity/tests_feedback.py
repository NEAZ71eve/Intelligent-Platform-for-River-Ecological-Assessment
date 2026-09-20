from datetime import timedelta

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from accounts.models import User

from .admin import FeedbackAdmin
from .models import Feedback
from .serializers import FeedbackSerializer
from .views import FeedbackView


class FeedbackAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='feedback-owner')
        cls.other = User.objects.create_user(username='feedback-other')
        cls.manager = User.objects.create_user(username='feedback-manager', is_staff=True)

    def setUp(self):
        self.api = APIClient()
        self.api.force_authenticate(self.owner)

    def create_feedback(self, **kwargs):
        return Feedback.objects.create(owner=self.owner, body='希望增加科普内容', **kwargs)

    def test_submit_trims_body_and_ignores_forged_owner_resolution_and_identity(self):
        response = self.api.post('/api/v1/feedback/', {
            'body': '  希望增加水资源文章 \n', 'owner': str(self.other.pk),
            'status': 'resolved', 'reply': '伪造管理员答复', 'resolved_at': timezone.now().isoformat(),
            'handled_by': str(self.manager.pk), 'id': '00000000-0000-0000-0000-000000000001',
        })
        self.assertEqual(response.status_code, 201, response.data)
        row = Feedback.objects.get(pk=response.data['id'])
        self.assertEqual(row.body, '希望增加水资源文章')
        self.assertEqual(row.owner, self.owner)
        self.assertEqual(row.status, 'pending')
        self.assertEqual(row.reply, '')
        self.assertIsNone(row.resolved_at)
        self.assertIsNone(row.handled_by)
        self.assertNotIn('handled_by', response.data)

    def test_body_requires_one_to_one_thousand_trimmed_characters(self):
        for body in ['', ' \n\t ', '文' * 1001]:
            with self.subTest(length=len(body)):
                self.assertEqual(self.api.post('/api/v1/feedback/', {'body': body}).status_code, 400)
        response = self.api.post('/api/v1/feedback/', {'body': ' ' + '文' * 1000 + ' '})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data['body']), 1000)
        self.assertEqual(self.api.post('/api/v1/feedback/', {}).status_code, 400)

    def test_list_is_private_and_cannot_be_redirected_with_owner_query(self):
        own = self.create_feedback()
        Feedback.objects.create(owner=self.other, body='SECRET_OTHER_FEEDBACK')
        response = self.api.get('/api/v1/feedback/', {'owner': self.other.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in response.data['data']], [str(own.pk)])
        self.assertEqual(response.data['meta']['count'], 1)

    def test_pending_answer_and_internal_handler_are_never_public(self):
        row = self.create_feedback(reply='管理员未发布草稿', handled_by=self.manager, resolved_at=timezone.now())
        payload = FeedbackSerializer(row).data
        self.assertEqual(payload['reply'], '')
        self.assertIsNone(payload['resolved_at'])
        self.assertNotIn('handled_by', payload)
        self.assertEqual(set(payload), {'id', 'body', 'status', 'created_at', 'reply', 'resolved_at'})

    def test_resolved_answer_and_time_are_visible_but_handler_is_private(self):
        at = timezone.now()
        row = self.create_feedback(status='resolved', reply='已补充学习稿', resolved_at=at, handled_by=self.manager)
        response = self.api.get('/api/v1/feedback/')
        payload = response.data['data'][0]
        self.assertEqual(payload['reply'], row.reply)
        self.assertIsNotNone(payload['resolved_at'])
        self.assertNotIn('handled_by', payload)

    def test_legacy_resolution_without_reply_or_time_keeps_its_status(self):
        row = self.create_feedback(status='resolved')
        response = self.api.get('/api/v1/feedback/')
        self.assertEqual(response.data['data'][0]['status'], 'resolved')
        self.assertEqual(response.data['data'][0]['reply'], '')
        self.assertIsNone(response.data['data'][0]['resolved_at'])
        row.refresh_from_db()
        self.assertEqual(row.status, 'resolved')

    def test_owner_can_delete_and_other_accounts_receive_not_found(self):
        row = self.create_feedback()
        self.api.force_authenticate(self.other)
        self.assertEqual(self.api.delete(f'/api/v1/feedback/{row.pk}/').status_code, 404)
        self.assertTrue(Feedback.objects.filter(pk=row.pk).exists())
        self.api.force_authenticate(self.owner)
        self.assertEqual(self.api.delete(f'/api/v1/feedback/{row.pk}/').status_code, 204)
        self.assertFalse(Feedback.objects.filter(pk=row.pk).exists())
        self.assertEqual(self.api.delete(f'/api/v1/feedback/{row.pk}/').status_code, 404)

    def test_user_cannot_patch_put_or_retrieve_detail(self):
        row = self.create_feedback()
        for method in ['patch', 'put']:
            self.assertEqual(getattr(self.api, method)(f'/api/v1/feedback/{row.pk}/', {'status': 'resolved'}).status_code, 405)
        self.assertEqual(self.api.get(f'/api/v1/feedback/{row.pk}/').status_code, 405)
        row.refresh_from_db()
        self.assertEqual(row.status, 'pending')

    def test_guest_cannot_read_submit_or_delete_feedback(self):
        row = self.create_feedback()
        self.api.force_authenticate(None)
        self.assertEqual(self.api.get('/api/v1/feedback/').status_code, 401)
        self.assertEqual(self.api.post('/api/v1/feedback/', {'body': '游客'}).status_code, 401)
        self.assertEqual(self.api.delete(f'/api/v1/feedback/{row.pk}/').status_code, 401)

    def test_pagination_has_stable_uuid_tie_breaker(self):
        rows = [self.create_feedback() for _ in range(3)]
        Feedback.objects.filter(owner=self.owner).update(created_at=timezone.now())
        actual = []
        for page in [1, 2, 3]:
            response = self.api.get('/api/v1/feedback/', {'page_size': 1, 'page': page})
            actual.append(response.data['data'][0]['id'])
            self.assertEqual(response.data['meta']['count'], 3)
        self.assertEqual(actual, sorted([str(row.pk) for row in rows], reverse=True))

    def test_account_deletion_removes_owned_feedback(self):
        row = self.create_feedback(status='resolved', reply='答复', resolved_at=timezone.now(), handled_by=self.manager)
        response = self.api.delete('/api/v1/me/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Feedback.objects.filter(pk=row.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.manager.pk).exists())

    def test_deleted_or_disabled_user_snapshot_cannot_submit(self):
        for action in ['delete', 'disable']:
            with self.subTest(action=action):
                user = User.objects.create_user(username=f'stale-feedback-{action}')
                stale = User.objects.get(pk=user.pk)
                if action == 'delete':
                    user.delete()
                else:
                    User.objects.filter(pk=user.pk).update(is_active=False)
                request = APIRequestFactory().post('/api/v1/feedback/', {'body': '认证后发生账号变更'})
                force_authenticate(request, user=stale)
                response = FeedbackView.as_view()(request)
                self.assertEqual(response.status_code, 401)
                self.assertFalse(Feedback.objects.filter(owner_id=stale.pk).exists())


class FeedbackAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='admin-feedback-owner')
        cls.editor = User.objects.create_user(username='feedback-editor', is_staff=True)
        cls.reader = User.objects.create_user(username='feedback-reader', is_staff=True)
        cls.other_editor = User.objects.create_user(username='feedback-second-editor', is_staff=True)
        view = Permission.objects.get(codename='view_feedback', content_type__app_label='activity')
        change = Permission.objects.get(codename='change_feedback', content_type__app_label='activity')
        cls.reader.user_permissions.add(view)
        cls.editor.user_permissions.add(view, change)
        cls.other_editor.user_permissions.add(view, change)

    def setUp(self):
        self.row = Feedback.objects.create(owner=self.owner, body='请补充路线科普')
        self.path = reverse('admin:activity_feedback_change', args=[self.row.pk])
        self.model_admin = FeedbackAdmin(Feedback, admin.site)
        self.client.force_login(self.editor)

    def test_resolve_requires_nonblank_reply_and_does_not_modify_on_invalid_form(self):
        for reply in ['', ' \n\t ', '文' * 1001]:
            with self.subTest(length=len(reply)):
                response = self.client.post(self.path, {'status': 'resolved', 'reply': reply, '_save': '保存'})
                self.assertEqual(response.status_code, 200)
                self.row.refresh_from_db()
                self.assertEqual(self.row.status, 'pending')
                self.assertIsNone(self.row.resolved_at)

    def test_resolve_sets_reply_handler_time_and_standard_admin_log(self):
        response = self.client.post(self.path, {'status': 'resolved', 'reply': '  已补充路线说明  ', '_save': '保存', 'owner': str(self.reader.pk), 'body': '伪造改写正文'})
        self.assertEqual(response.status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, 'resolved')
        self.assertEqual(self.row.reply, '已补充路线说明')
        self.assertEqual(self.row.owner, self.owner)
        self.assertEqual(self.row.body, '请补充路线科普')
        self.assertEqual(self.row.handled_by, self.editor)
        self.assertIsNotNone(self.row.resolved_at)
        log = LogEntry.objects.get(object_id=str(self.row.pk))
        self.assertEqual(log.user, self.editor)
        self.assertNotIn(self.row.reply, log.change_message)

    def test_view_only_staff_cannot_process_and_direct_save_guard_denies_it(self):
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get(self.path).status_code, 200)
        self.assertEqual(self.client.post(self.path, {'status': 'resolved', 'reply': '无权限答复'}).status_code, 403)
        request = RequestFactory().post(self.path)
        request.user = self.reader
        self.row.status, self.row.reply = 'resolved', '无权限答复'
        with self.assertRaises(PermissionDenied):
            self.model_admin.save_model(request, self.row, None, True)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, 'pending')

    def test_reopen_clears_processing_metadata_and_hides_saved_reply(self):
        self.row.status, self.row.reply = 'resolved', '之前的处理答复'
        self.row.resolved_at, self.row.handled_by = timezone.now(), self.editor
        self.row.save()
        response = self.client.post(self.path, {'status': 'pending', 'reply': '补充答复草稿', '_save': '保存'})
        self.assertEqual(response.status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, 'pending')
        self.assertIsNone(self.row.resolved_at)
        self.assertIsNone(self.row.handled_by)
        self.assertEqual(FeedbackSerializer(self.row).data['reply'], '')

    def test_answer_edit_refreshes_handler_and_time_but_unchanged_save_preserves_them(self):
        old_time = timezone.now() - timedelta(days=1)
        self.row.status, self.row.reply = 'resolved', '原答复'
        self.row.resolved_at, self.row.handled_by = old_time, self.editor
        self.row.save()
        self.client.force_login(self.other_editor)
        response = self.client.post(self.path, {'status': 'resolved', 'reply': '原答复', '_save': '保存'})
        self.assertEqual(response.status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.handled_by, self.editor)
        self.assertEqual(self.row.resolved_at, old_time)
        self.client.post(self.path, {'status': 'resolved', 'reply': '修订答复', '_save': '保存'})
        self.row.refresh_from_db()
        self.assertEqual(self.row.handled_by, self.other_editor)
        self.assertGreater(self.row.resolved_at, old_time)

    def test_historical_resolved_record_needs_reply_when_saved_again(self):
        self.row.status = 'resolved'
        self.row.save()
        self.assertEqual(self.client.get(self.path).status_code, 200)
        response = self.client.post(self.path, {'status': 'resolved', 'reply': '', '_save': '保存'})
        self.assertEqual(response.status_code, 200)
        self.row.refresh_from_db()
        self.assertIsNone(self.row.resolved_at)
        response = self.client.post(self.path, {'status': 'resolved', 'reply': '补录处理答复', '_save': '保存'})
        self.assertEqual(response.status_code, 302)
        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.resolved_at)

    def test_deleting_handler_preserves_owner_feedback_and_resolved_reply(self):
        self.row.status, self.row.reply = 'resolved', '已处理'
        self.row.resolved_at, self.row.handled_by = timezone.now(), self.editor
        self.row.save()
        self.editor.delete()
        self.row.refresh_from_db()
        self.assertIsNone(self.row.handled_by)
        self.assertEqual(self.row.reply, '已处理')
        self.assertEqual(self.row.owner, self.owner)

    def test_staff_cannot_add_feedback_from_admin(self):
        request = RequestFactory().get('/admin/')
        request.user = self.editor
        self.assertFalse(self.model_admin.has_add_permission(request))
        self.assertEqual(self.client.get(reverse('admin:activity_feedback_add')).status_code, 403)
