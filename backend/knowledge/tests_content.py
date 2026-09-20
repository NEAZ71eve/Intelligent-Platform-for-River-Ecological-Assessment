import json
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from ecology.models import Place, Region

from .models import Content
from .views import ContentDetail, ContentList, ContentTags


class ContentDiscoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.region = Region.objects.create(slug="discovery-region", name="科普一区")
        cls.other_region = Region.objects.create(slug="discovery-other", name="科普二区")
        cls.place = Place.objects.create(region=cls.region, slug="discovery-garden", name="学习园", kind="plant")
        cls.other_place = Place.objects.create(region=cls.other_region, slug="other-garden", name="另一区学习园", kind="plant")
        cls.hidden_place = Place.objects.create(region=cls.region, slug="hidden-garden", name="SECRET_HIDDEN_PLACE", kind="plant", is_published=False)
        cls.at = timezone.now()

        def article(slug, **kwargs):
            return Content.objects.create(slug=slug, title=f"观察 {slug}", body="正文不会参与标题和摘要搜索", summary="植物观察摘要", category="plants", status="published", published_at=cls.at, **kwargs)

        cls.local = article("local-daisy", place=cls.place, plant_label="daisy", source="管理员原创记录")
        cls.global_article = article("global-daisy", plant_label="daisy")
        cls.other = article("other-daisy", place=cls.other_place, plant_label="daisy")
        cls.hidden_link = article("hidden-link", place=cls.hidden_place, plant_label="custom_tree")
        cls.custom = article("custom-plant", plant_label="custom_tree")
        cls.draft = Content.objects.create(slug="secret-draft", title="SECRET_DRAFT", body="草稿", plant_label="secret_label")
        cls.water = Content.objects.create(slug="water-learning", title="水环境学习", body="水文", summary="溶解氧", category="water", status="published", place=cls.place, published_at=cls.at)

    def setUp(self):
        self.factory = APIRequestFactory()

    def listing(self, params=None):
        return ContentList.as_view()(self.factory.get("/api/v1/contents/", params or {}))

    def tags(self, params=None):
        return ContentTags.as_view()(self.factory.get("/api/v1/content-tags/", params or {}))

    def ids(self, response):
        self.assertEqual(response.status_code, 200, response.data)
        return {row["id"] for row in response.data["data"]}

    def test_combined_filters_intersect_and_search_title_or_summary(self):
        response = self.listing({"category": "plants", "plant_label": "daisy", "place": self.place.slug, "region": str(self.region.pk), "search": "local-daisy"})
        self.assertEqual(self.ids(response), {str(self.local.pk)})
        response = self.listing({"category": "plants", "place": self.place.slug, "search": " 植物观察摘要 "})
        self.assertEqual(self.ids(response), {str(self.local.pk)})
        self.assertEqual(self.ids(self.listing({"category": "plants", "search": "正文不会"})), set())

    def test_region_includes_only_public_local_and_genuinely_global_articles(self):
        expected = {str(row.pk) for row in [self.local, self.global_article, self.custom, self.water]}
        self.assertEqual(self.ids(self.listing({"region": self.region.slug})), expected)
        self.assertEqual(self.ids(self.listing({"region": str(self.region.pk)})), expected)
        self.assertNotIn(str(self.hidden_link.pk), expected)

    def test_no_region_filter_keeps_published_article_with_hidden_association(self):
        self.assertIn(str(self.hidden_link.pk), self.ids(self.listing()))
        self.assertNotIn(str(self.draft.pk), self.ids(self.listing()))

    def test_place_filter_accepts_uuid_and_slug_but_never_adds_global_articles(self):
        expected = {str(self.local.pk), str(self.water.pk)}
        for value in [self.place.slug, str(self.place.pk)]:
            self.assertEqual(self.ids(self.listing({"place": value})), expected)
        self.assertEqual(self.ids(self.listing({"place": self.place.slug, "region": self.other_region.slug})), set())

    def test_hidden_and_unknown_places_have_same_public_error(self):
        responses = [self.listing({"place": value}) for value in [self.hidden_place.slug, str(self.hidden_place.pk), "unknown-place"]]
        self.assertTrue(all(response.status_code == 404 for response in responses))
        self.assertEqual(responses[0].data, responses[2].data)

    def test_invalid_filters_are_explicit_and_duplicate_selectors_rejected(self):
        for params in [{"category": "nope"}, {"plant_label": "bad label"}, {"plant_label": "x" * 51}, {"search": "x" * 101}]:
            with self.subTest(params=params):
                self.assertEqual(self.listing(params).status_code, 400)
                self.assertEqual(self.tags(params).status_code, 400)
        self.assertEqual(self.listing({"region": "unknown-region"}).status_code, 404)
        for field in ["category", "plant_label", "place", "region", "search"]:
            with self.subTest(field=field):
                response = ContentList.as_view()(self.factory.get(f"/api/v1/contents/?{field}=one&{field}=two"))
                self.assertEqual(response.status_code, 400)

    def test_unknown_well_formed_label_produces_empty_results(self):
        self.assertEqual(self.ids(self.listing({"plant_label": "not-in-catalogue"})), set())
        self.assertEqual(self.tags({"plant_label": "not-in-catalogue"}).data, {"categories": [], "plant_labels": [], "content_count": 0})

    def test_detail_redacts_hidden_place_id_and_summary_without_hiding_article(self):
        response = ContentDetail.as_view()(self.factory.get("/api/v1/contents/"), pk=self.hidden_link.pk)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["place"])
        self.assertIsNone(response.data["place_summary"])
        rendered = json.dumps(response.data, default=str)
        self.assertNotIn(str(self.hidden_place.pk), rendered)
        self.assertNotIn(self.hidden_place.name, rendered)

    def test_public_place_summary_and_source_are_available_without_login(self):
        response = ContentDetail.as_view()(self.factory.get("/api/v1/contents/"), pk=self.local.pk)
        self.assertEqual(response.data["place"], str(self.place.pk))
        self.assertEqual(response.data["place_summary"]["name"], self.place.name)
        self.assertEqual(response.data["place_summary"]["region"], str(self.region.pk))
        self.assertEqual(response.data["source"], "管理员原创记录")
        global_response = ContentDetail.as_view()(self.factory.get("/api/v1/contents/"), pk=self.global_article.pk)
        self.assertIsNone(global_response.data["place_summary"])

    def test_hidden_place_is_redacted_in_list_and_draft_detail_is_unavailable(self):
        body = json.dumps(self.listing().data, default=str)
        self.assertNotIn(str(self.hidden_place.pk), body)
        self.assertNotIn(self.hidden_place.name, body)
        response = ContentDetail.as_view()(self.factory.get("/api/v1/contents/"), pk=self.draft.pk)
        self.assertEqual(response.status_code, 404)

    def test_tag_counts_share_filters_and_ignore_drafts(self):
        tags = self.tags({"region": self.region.slug}).data
        self.assertEqual(tags["content_count"], 4)
        self.assertEqual(tags["categories"], [{"value": "plants", "name": "植物知识", "count": 3}, {"value": "water", "name": "水资源保护", "count": 1}])
        self.assertEqual(tags["plant_labels"], [{"value": "custom_tree", "name": "custom_tree", "count": 1}, {"value": "daisy", "name": "雏菊类花卉", "count": 2}])
        self.assertNotIn("secret_label", json.dumps(tags))
        combined = self.tags({"place": self.place.slug, "category": "plants", "plant_label": "daisy", "search": "local-daisy"}).data
        self.assertEqual(combined["content_count"], 1)
        self.assertEqual(combined["plant_labels"][0]["count"], 1)

    def test_empty_search_and_empty_optional_selectors_match_unfiltered_catalogue(self):
        self.assertEqual(self.ids(self.listing({"search": "   ", "category": "", "place": ""})), self.ids(self.listing()))

    def test_pagination_ties_have_stable_unique_order_and_null_dates_are_last(self):
        Content.objects.filter(status="published").update(created_at=self.at)
        Content.objects.filter(pk=self.local.pk).update(published_at=self.at + timedelta(days=1))
        Content.objects.filter(pk=self.global_article.pk).update(published_at=None)
        expected = [str(self.local.pk)] + sorted(str(row.pk) for row in [self.other, self.hidden_link, self.custom, self.water]) + [str(self.global_article.pk)]
        actual = []
        for page in range(1, 4):
            response = self.listing({"page_size": 2, "page": page})
            actual.extend(row["id"] for row in response.data["data"])
            self.assertEqual(response.data["meta"]["count"], 6)
        self.assertEqual(actual, expected)
        self.assertEqual(self.listing({"page_size": 2, "page": 4}).status_code, 404)

    def test_place_summaries_do_not_add_queries_per_article(self):
        with self.assertNumQueries(2):
            response = self.listing()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.data["data"]), 6)
        with self.assertNumQueries(1):
            response = ContentDetail.as_view()(self.factory.get("/api/v1/contents/"), pk=self.local.pk)
            self.assertEqual(response.status_code, 200)
