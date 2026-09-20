from unittest.mock import patch
from urllib.parse import urlsplit

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from accounts.services import issue_session
from ecology.models import Place, Region
from .models import Favorite, History, Visit
from .serializers import TargetInput


class PersonalRecordTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='records-owner')
        self.other = User.objects.create_user(username='records-other')
        self.api = APIClient()
        self.token, _ = issue_session(self.user)
        self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        self.region = Region.objects.create(slug='records-region', name='记录测试区域')
        self.places = [Place.objects.create(region=self.region, slug=f'record-place-{i}', name=f'地点 {i}', kind='park') for i in range(5)]

    def test_all_record_lists_have_stable_timestamp_ties_and_real_pagination_contract(self):
        timestamp = timezone.now()
        for model, endpoint, field in ((Favorite, 'favorites', 'created_at'), (History, 'histories', 'viewed_at'), (Visit, 'visits', 'visited_at')):
            with self.subTest(endpoint=endpoint):
                own = [model.objects.create(owner=self.user, place=place) for place in self.places]
                model.objects.create(owner=self.other, place=self.places[0])
                model.objects.filter(owner=self.user).update(**{field: timestamp})
                expected = sorted([str(row.pk) for row in own], reverse=True)
                path = f'/api/v1/{endpoint}/?page_size=2'
                seen = []
                while path:
                    response = self.api.get(path)
                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertEqual(payload['meta']['count'], 5)
                    self.assertEqual(payload['meta']['page_size'], 2)
                    seen.extend(row['id'] for row in payload['data'])
                    next_url = payload['meta']['next']
                    if next_url:
                        parts = urlsplit(next_url)
                        self.assertEqual(parts.path, f'/api/v1/{endpoint}/')
                        path = parts.path + '?' + parts.query
                    else:
                        path = None
                self.assertEqual(seen, expected)
                self.assertEqual(len(set(seen)), 5)

    def test_unpublished_place_records_keep_no_private_title_and_remain_deletable(self):
        place = self.places[0]
        for model in (Favorite, History, Visit):
            model.objects.create(owner=self.user, place=place)
        place.is_published = False
        place.save()
        for endpoint in ('favorites', 'histories', 'visits'):
            with self.subTest(endpoint=endpoint):
                response = self.api.get(f'/api/v1/{endpoint}/')
                row = response.json()['data'][0]
                self.assertIsNone(row['place'])
                self.assertNotIn(place.name, response.content.decode())
                self.assertEqual(self.api.post(f'/api/v1/{endpoint}/', {'place_id': str(place.pk)}).status_code, 400)
                self.assertEqual(self.api.delete(f'/api/v1/{endpoint}/{row["id"]}/').status_code, 204)
                self.assertEqual(self.api.delete(f'/api/v1/{endpoint}/{row["id"]}/').status_code, 404)

    def test_foreign_records_cannot_be_listed_or_deleted_and_guests_are_denied(self):
        guest = APIClient()
        for model, endpoint in ((Favorite, 'favorites'), (History, 'histories'), (Visit, 'visits')):
            with self.subTest(endpoint=endpoint):
                row = model.objects.create(owner=self.other, place=self.places[0])
                self.assertEqual(self.api.get(f'/api/v1/{endpoint}/').json()['data'], [])
                self.assertEqual(self.api.delete(f'/api/v1/{endpoint}/{row.pk}/').status_code, 404)
                self.assertTrue(model.objects.filter(pk=row.pk).exists())
                self.assertEqual(guest.get(f'/api/v1/{endpoint}/').status_code, 401)
                self.assertEqual(guest.post(f'/api/v1/{endpoint}/', {'place_id': str(self.places[0].pk)}).status_code, 401)

    def test_repeat_history_advances_it_to_first_page_without_creating_a_duplicate(self):
        old = History.objects.create(owner=self.user, place=self.places[0], viewed_at=timezone.now() - timezone.timedelta(days=2))
        History.objects.create(owner=self.user, place=self.places[1])
        response = self.api.post('/api/v1/histories/', {'place_id': str(self.places[0].pk)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['id'], str(old.pk))
        self.assertEqual(History.objects.filter(owner=self.user).count(), 2)
        self.assertEqual(self.api.get('/api/v1/histories/?page_size=1').json()['data'][0]['id'], str(old.pk))

    def test_deleted_target_removes_associated_records_without_leaking_old_details(self):
        place = self.places[0]
        for model in (Favorite, History, Visit):
            model.objects.create(owner=self.user, place=place)
        place.delete()
        for endpoint in ('favorites', 'histories', 'visits'):
            self.assertEqual(self.api.get(f'/api/v1/{endpoint}/').json()['data'], [])

    def test_deleted_owner_after_authentication_returns_401_instead_of_500(self):
        validate = TargetInput.validate
        for model, endpoint in ((Favorite, 'favorites'), (History, 'histories'), (Visit, 'visits')):
            with self.subTest(endpoint=endpoint):
                owner = User.objects.create_user(username=f'deleted-{endpoint}')
                token, _ = issue_session(owner)
                self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

                def delete_after_validation(serializer, attrs):
                    result = validate(serializer, attrs)
                    User.objects.filter(pk=owner.pk).delete()
                    return result

                with patch.object(TargetInput, 'validate', delete_after_validation):
                    response = self.api.post(f'/api/v1/{endpoint}/', {'place_id': str(self.places[0].pk)})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()['error']['code'], 'AUTH_REQUIRED')
                self.assertFalse(model.objects.filter(owner_id=owner.pk).exists())

    def test_owner_deactivated_during_request_cannot_create_a_record(self):
        validate = TargetInput.validate

        def deactivate_after_validation(serializer, attrs):
            result = validate(serializer, attrs)
            User.objects.filter(pk=self.user.pk).update(is_active=False)
            return result

        with patch.object(TargetInput, 'validate', deactivate_after_validation):
            response = self.api.post('/api/v1/favorites/', {'place_id': str(self.places[0].pk)})
        self.assertEqual(response.status_code, 401)
        self.assertFalse(Favorite.objects.filter(owner=self.user).exists())
