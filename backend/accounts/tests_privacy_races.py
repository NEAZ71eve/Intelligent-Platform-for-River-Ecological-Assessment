"""Privacy writes and account deletion serialize on the current database owner."""
import threading
from unittest import skipUnless

from django.db import connection, connections, transaction
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from activity.models import Favorite, Feedback, History, Visit
from activity.views import FeedbackView, HistoryView, RecordsView, VisitsView
from ecology.models import Place, Region
from .models import User
from .views import MeView


class StalePrivacyIdentityTests(TestCase):
    def request(self, user, method, data=None):
        request = getattr(APIRequestFactory(), method)('/api/v1/me/', data or {}, format='json')
        force_authenticate(request, user=user)
        return MeView.as_view()(request)

    def test_profile_update_rejects_deleted_or_disabled_authenticated_snapshot(self):
        for change in ('delete', 'disable'):
            with self.subTest(change=change):
                user = User.objects.create_user(username=f'privacy-update-{change}')
                snapshot = User.objects.get(pk=user.pk)
                if change == 'delete':
                    User.objects.filter(pk=user.pk).delete()
                else:
                    User.objects.filter(pk=user.pk).update(is_active=False)
                response = self.request(snapshot, 'patch', {'record_history': False})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.data['error']['code'], 'AUTH_REQUIRED')
                if change == 'disable':
                    user.refresh_from_db()
                    self.assertTrue(user.record_history)

    def test_account_delete_rejects_deleted_or_disabled_authenticated_snapshot(self):
        for change in ('delete', 'disable'):
            with self.subTest(change=change):
                user = User.objects.create_user(username=f'privacy-delete-{change}')
                snapshot = User.objects.get(pk=user.pk)
                if change == 'delete':
                    User.objects.filter(pk=user.pk).delete()
                else:
                    User.objects.filter(pk=user.pk).update(is_active=False)
                response = self.request(snapshot, 'delete')
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.data['error']['code'], 'AUTH_REQUIRED')
                if change == 'disable':
                    self.assertTrue(User.objects.filter(pk=user.pk).exists())

    def test_account_delete_rechecks_staff_protection_after_authentication(self):
        user = User.objects.create_user(username='privacy-promoted-admin')
        snapshot = User.objects.get(pk=user.pk)
        User.objects.filter(pk=user.pk).update(is_staff=True)
        response = self.request(snapshot, 'delete')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['error']['code'], 'ACCOUNT_PROTECTED')
        self.assertTrue(User.objects.filter(pk=user.pk).exists())


@skipUnless(connection.vendor == 'postgresql', 'Requires real PostgreSQL row locks and deferred foreign keys')
class ConcurrentPrivacyDeletionTests(TransactionTestCase):
    def test_deletion_serializes_before_cascade_collection_when_private_records_are_committing(self):
        owner = User.objects.create_user(username='privacy-concurrent-owner')
        owner_id = owner.pk
        region = Region.objects.create(slug='privacy-concurrent-region', name='并发验证区')
        place = Place.objects.create(region=region, slug='privacy-concurrent-place', name='公开地点', kind='park')
        delete_reached_owner = threading.Event()
        outcome = {}

        def observe_owner_statement(execute, sql, params, many, context):
            # Before the fix, this is the late parent DELETE, after child tables
            # were scanned. With the fix, it is SELECT FOR UPDATE before collecting
            # children. Both block behind the writer until its outer transaction commits.
            if '"accounts_user"' in sql and (sql.startswith('DELETE FROM "accounts_user"') or (sql.startswith('SELECT') and 'FOR UPDATE' in sql)):
                delete_reached_owner.set()
            return execute(sql, params, many, context)

        def delete_account():
            connections.close_all()
            try:
                snapshot = User.objects.get(pk=owner_id)
                request = APIRequestFactory().delete('/api/v1/me/')
                force_authenticate(request, user=snapshot)
                with connections['default'].execute_wrapper(observe_owner_statement):
                    outcome['status'] = MeView.as_view()(request).status_code
            except Exception as exc:  # Pass the actual database exception back to the test thread.
                outcome['error'] = exc
            finally:
                connections['default'].close()

        thread = threading.Thread(target=delete_account, daemon=True)
        reached = False
        with transaction.atomic():
            for view, endpoint, body in (
                (FeedbackView, 'feedback', {'body': '注销并发验证'}),
                (RecordsView, 'favorites', {'place_id': str(place.pk)}),
                (HistoryView, 'histories', {'place_id': str(place.pk)}),
                (VisitsView, 'visits', {'place_id': str(place.pk)}),
            ):
                request = APIRequestFactory().post(f'/api/v1/{endpoint}/', body, format='json')
                force_authenticate(request, user=owner)
                self.assertEqual(view.as_view()(request).status_code, 201)
            thread.start()
            reached = delete_reached_owner.wait(10)
        thread.join(10)
        self.assertTrue(reached, 'Account deletion did not reach its owner-lock/delete statement')
        self.assertFalse(thread.is_alive(), 'Account deletion remained blocked after the writer committed')
        self.assertNotIn('error', outcome, repr(outcome.get('error')))
        self.assertEqual(outcome.get('status'), 204)
        self.assertFalse(User.objects.filter(pk=owner_id).exists())
        for model in (Feedback, Favorite, History, Visit):
            self.assertFalse(model.objects.filter(owner_id=owner_id).exists(), model.__name__)

    def test_profile_write_keeps_owner_locked_until_audit_is_recorded(self):
        from unittest.mock import patch
        from django.db import OperationalError
        from common.audit import audit as write_audit

        owner = User.objects.create_user(username='privacy-profile-audit-owner')
        owner_id = owner.pk
        probed = threading.Event()
        deleted = threading.Event()
        outcome = {}

        def delete_account():
            connections.close_all()
            request = APIRequestFactory().delete('/api/v1/me/')
            force_authenticate(request, user=User.objects.get(pk=owner_id))
            try:
                try:
                    with transaction.atomic():
                        User.objects.select_for_update(nowait=True).get(pk=owner_id)
                        outcome['probe'] = 'unlocked'
                        probed.set()
                        outcome['status'] = MeView.as_view()(request).status_code
                except OperationalError as exc:
                    if getattr(exc.__cause__, 'sqlstate', None) != '55P03':
                        raise
                    outcome['probe'] = 'locked'
                    probed.set()
                    # Wait for the profile transaction to finish, then delete normally.
                    outcome['status'] = MeView.as_view()(request).status_code
            except Exception as exc:
                outcome['error'] = exc
            finally:
                probed.set()
                deleted.set()
                connections['default'].close()

        thread = threading.Thread(target=delete_account, daemon=True)

        def interleave_before_audit(event, actor=None, **kwargs):
            if event == 'user.profile_updated':
                thread.start()
                if not probed.wait(10):
                    raise AssertionError('Delete transaction did not probe the owner lock')
                if outcome.get('probe') == 'unlocked' and not deleted.wait(10):
                    raise AssertionError('Unlocked owner could not be deleted')
            return write_audit(event, actor, **kwargs)

        request = APIRequestFactory().patch('/api/v1/me/', {'record_history': False}, format='json')
        force_authenticate(request, user=owner)
        try:
            with patch('accounts.views.audit', interleave_before_audit):
                response = MeView.as_view()(request)
        finally:
            if thread.ident is not None:
                thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertNotIn('error', outcome, repr(outcome.get('error')))
        self.assertEqual(outcome.get('probe'), 'locked')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(outcome.get('status'), 204)
        self.assertFalse(User.objects.filter(pk=owner_id).exists())
