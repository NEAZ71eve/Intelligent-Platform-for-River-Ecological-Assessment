import io
import json

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from ecology.models import Place

from .models import Content, Route
from .views import ContentDetail, ContentList, RouteDetail


class PublicationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", no_observations=True, stdout=io.StringIO())
        cls.draft = Content.objects.create(title="SECRET_DRAFT_CONTENT", slug="draft-content", body="unpublished")
        cls.unpublished_route = Route.objects.create(region=Place.objects.first().region, slug="draft-route", title="SECRET_ROUTE")

    def setUp(self):
        self.factory = APIRequestFactory()

    def test_public_list_and_detail_hide_drafts(self):
        response = ContentList.as_view()(self.factory.get("/api/v1/contents/"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("SECRET_DRAFT_CONTENT", json.dumps(response.data, default=str))
        response = ContentDetail.as_view()(self.factory.get("/api/v1/contents/"), pk=self.draft.pk)
        self.assertEqual(response.status_code, 404)
        response = RouteDetail.as_view()(self.factory.get("/api/v1/routes/"), pk=self.unpublished_route.pk)
        self.assertEqual(response.status_code, 404)

    def test_unpublished_route_stop_place_does_not_leak(self):
        route = Route.objects.get(slug="campus-eco-walk")
        place = route.stops.first().place
        place.is_published = False
        place.save()
        response = RouteDetail.as_view()(self.factory.get("/api/v1/routes/"), pk=route.pk)
        self.assertNotIn(str(place.pk), json.dumps(response.data, default=str))
