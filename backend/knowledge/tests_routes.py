import json

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from ecology.models import Place, Region, WaterBody

from .models import Route, RouteStop
from .views import RouteDetail, RouteList


class PublicRouteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.region = Region.objects.create(slug="route-region", name="路线一区")
        cls.other_region = Region.objects.create(slug="route-other", name="路线二区")
        cls.first = Place.objects.create(region=cls.region, slug="route-start", name="起点", kind="campus")
        cls.second = Place.objects.create(region=cls.region, slug="route-river", name="河流学习点", kind="river")
        cls.water = WaterBody.objects.create(place=cls.second)
        cls.hidden = Place.objects.create(region=cls.region, slug="route-hidden", name="SECRET_HIDDEN_STOP", kind="park", is_published=False)
        cls.foreign = Place.objects.create(region=cls.other_region, slug="other-route-place", name="异区地点", kind="park")
        cls.route = Route.objects.create(region=cls.region, slug="local-route", title="生态学习路线", published=True, source="管理员原创路线", is_demo=True)
        # Insert out of order to prove the API uses explicit route order.
        cls.last_stop = RouteStop.objects.create(route=cls.route, place=cls.second, order=7, note="读河流介绍")
        cls.first_stop = RouteStop.objects.create(route=cls.route, place=cls.first, order=2, note="从入口开始")
        cls.hidden_stop = RouteStop.objects.create(route=cls.route, place=cls.hidden, order=5, note="SECRET_HIDDEN_NOTE")
        cls.empty_route = Route.objects.create(region=cls.region, slug="empty-route", title="生态学习路线", published=True)
        cls.other_route = Route.objects.create(region=cls.other_region, slug="other-route", title="异区生态路线", published=True)
        RouteStop.objects.create(route=cls.other_route, place=cls.foreign, order=1)
        cls.draft = Route.objects.create(region=cls.region, slug="secret-route", title="SECRET_DRAFT_ROUTE")

    def setUp(self):
        self.factory = APIRequestFactory()

    def listing(self, params=None):
        return RouteList.as_view()(self.factory.get("/api/v1/routes/", params or {}))

    def detail(self, route=None):
        return RouteDetail.as_view()(self.factory.get("/api/v1/routes/"), pk=(route or self.route).pk)

    def test_region_filter_accepts_slug_and_uuid_without_adding_other_regions(self):
        for value in [self.region.slug, str(self.region.pk)]:
            response = self.listing({"region": value})
            self.assertEqual(response.status_code, 200)
            self.assertEqual({row["id"] for row in response.data["data"]}, {str(self.route.pk), str(self.empty_route.pk)})
        self.assertEqual(self.listing().data["meta"]["count"], 3)

    def test_unknown_region_and_duplicate_selector_rejected(self):
        self.assertEqual(self.listing({"region": "unknown-region"}).status_code, 404)
        response = RouteList.as_view()(self.factory.get("/api/v1/routes/?region=one&region=two"))
        self.assertEqual(response.status_code, 400)

    def test_public_stops_keep_original_order_with_gaps_and_safe_count(self):
        response = self.detail()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["stop_count"], 2)
        self.assertEqual([stop["order"] for stop in response.data["stops"]], [2, 7])
        self.assertEqual([stop["place"]["id"] for stop in response.data["stops"]], [str(self.first.pk), str(self.second.pk)])
        self.assertEqual(response.data["stops"][1]["place"]["water_body_id"], str(self.water.pk))

    def test_hidden_nodes_do_not_leak_names_ids_notes_or_count(self):
        for response in [self.detail(), self.listing()]:
            body = json.dumps(response.data, default=str)
            for hidden_value in [self.hidden.name, str(self.hidden.pk), str(self.hidden_stop.pk), self.hidden_stop.note]:
                self.assertNotIn(hidden_value, body)
        self.assertEqual(self.detail().data["stop_count"], 2)

    def test_removed_and_newly_hidden_nodes_disappear_on_next_request(self):
        self.first_stop.delete()
        response = self.detail()
        self.assertEqual(response.data["stop_count"], 1)
        self.assertEqual(response.data["stops"][0]["order"], 7)
        self.second.is_published = False
        self.second.save()
        response = self.detail()
        self.assertEqual(response.data["stop_count"], 0)
        self.assertEqual(response.data["stops"], [])

    def test_empty_route_and_provenance_are_explicit(self):
        self.assertEqual(self.detail(self.empty_route).data["stops"], [])
        self.assertEqual(self.detail(self.empty_route).data["stop_count"], 0)
        response = self.detail()
        self.assertEqual(response.data["source"], "管理员原创路线")
        self.assertTrue(response.data["is_demo"])
        self.assertEqual(response.data["region_name"], self.region.name)

    def test_unpublished_route_is_absent_from_list_and_detail(self):
        self.assertNotIn("SECRET_DRAFT_ROUTE", json.dumps(self.listing().data, default=str))
        self.assertEqual(self.detail(self.draft).status_code, 404)
        self.route.published = False
        self.route.save()
        self.assertEqual(self.detail().status_code, 404)

    def test_same_title_routes_have_stable_pagination(self):
        expected = sorted([str(self.route.pk), str(self.empty_route.pk)])
        actual = []
        for page in [1, 2]:
            response = self.listing({"region": self.region.slug, "page_size": 1, "page": page})
            self.assertEqual(response.data["meta"]["count"], 2)
            actual.append(response.data["data"][0]["id"])
        self.assertEqual(actual, expected)

    def test_prefetch_keeps_list_and_detail_query_count_constant(self):
        with self.assertNumQueries(3):
            response = self.listing()
            self.assertEqual(len(response.data["data"]), 3)
            self.assertEqual(sum(row["stop_count"] for row in response.data["data"]), 3)
        with self.assertNumQueries(2):
            self.assertEqual(self.detail().data["stop_count"], 2)

    def test_inconsistent_imported_cross_region_node_is_not_public(self):
        # Normal writes reject this relation. Public reads also contain legacy
        # or externally imported data without exposing an unrelated place.
        RouteStop.objects.filter(pk=self.first_stop.pk).update(place=self.foreign)
        response = self.detail()
        self.assertEqual(response.data["stop_count"], 1)
        self.assertNotIn(str(self.foreign.pk), json.dumps(response.data, default=str))
