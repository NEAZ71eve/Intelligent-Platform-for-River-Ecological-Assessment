import csv
import io
import tempfile
from datetime import datetime, timedelta, timezone as datetime_timezone
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, APIClient
from django.utils import timezone as django_timezone

from .models import AssessmentJob, DataSource, MapLayout, Metric, Observation, Place, Region, RuleSet, SimulationRun, SimulationScenario, Station, WaterBody
from .simulation import generate, observation_key
from .views import AirQuality, EnvironmentalSummary, ObservationList, WeatherAlerts

START = datetime(2026, 9, 15, tzinfo=datetime_timezone.utc)


class DemoDataTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", no_observations=True, stdout=io.StringIO())


class DomainIntegrityTests(DemoDataTestCase):
    def test_seed_is_idempotent_and_preserves_admin_edits(self):
        place = Place.objects.get(slug="library")
        place.description = "管理员维护内容"
        place.save()
        call_command("seed_demo", no_observations=True, stdout=io.StringIO())
        self.assertEqual(Place.objects.count(), 12)
        self.assertEqual(Station.objects.count(), 4)
        self.assertEqual(WaterBody.objects.count(), 2)
        place.refresh_from_db()
        self.assertEqual(place.description, "管理员维护内容")

    def test_multiple_stations_can_belong_to_one_water_body(self):
        base = Station.objects.get(code="demo-water-01")
        Station.objects.create(region=base.region, place=base.place, water_body=base.water_body, name="另一断面", code="water-second-section", kind="water")
        self.assertEqual(base.water_body.stations.count(), 2)

    def test_reject_cross_region_station_and_route_relations(self):
        from knowledge.models import Route, RouteStop
        other = Region.objects.create(slug="other", name="其他示范区")
        base = Station.objects.get(code="demo-water-01")
        with self.assertRaises(ValidationError):
            Station.objects.create(region=other, water_body=base.water_body, code="bad-station", name="错误关系", kind="water")
        route = Route.objects.create(region=other, slug="other-route", title="其他路线")
        with self.assertRaises(ValidationError):
            RouteStop.objects.create(route=route, place=base.place, order=1)

    def test_reject_invalid_map_coordinates(self):
        place = Place.objects.get(slug="library")
        place.x_ratio = float("nan")
        with self.assertRaises(ValidationError):
            place.save()
        place.x_ratio = 0.5
        other = Region.objects.create(slug="other", name="其他示范区")
        place.map_layout = MapLayout.objects.create(region=other, name="其他底图")
        with self.assertRaises(ValidationError):
            place.save()

    def test_metric_unit_cannot_relabel_existing_observations(self):
        generate("normal", START, 1, seed=7)
        metric = Metric.objects.get(code="temperature")
        metric.unit = "°F"
        with self.assertRaises(ValidationError):
            metric.save()

    def test_source_type_cannot_relabel_existing_observations(self):
        generate("normal", START, 1, seed=7)
        source = DataSource.objects.get(code="demo-normal")
        source.kind = "api"
        with self.assertRaises(ValidationError):
            source.save()

    def test_historical_identity_and_parent_relations_cannot_drift(self):
        from knowledge.models import Route
        generate("normal", START, 1, seed=7)
        station = Station.objects.get(code="demo-water-01")
        station.code = "renamed-source-of-duplicate-imports"
        with self.assertRaises(ValidationError):
            station.save()
        river = WaterBody.objects.get(place__slug="clear-river")
        river.place = Place.objects.get(slug="mirror-lake")
        with self.assertRaises(ValidationError):
            river.save()
        route = Route.objects.get(slug="campus-eco-walk")
        route.region = Region.objects.create(slug="other", name="其他区域")
        with self.assertRaises(ValidationError):
            route.save()


class SimulationTests(DemoDataTestCase):
    def test_replay_is_deterministic_and_same_batch_is_idempotent(self):
        run, created = generate("normal", START, 24, seed=17)
        self.assertTrue(created)
        self.assertEqual(run.counts, 24 * 13)
        replay, created = generate("normal", START, 24, seed=17)
        self.assertFalse(created)
        self.assertEqual(run.pk, replay.pk)
        self.assertEqual(Observation.objects.count(), 24 * 13)
        extended, _ = generate("normal", START, 48, seed=17)
        values = lambda query: list(query.order_by("observed_at", "station__code", "metric__code").values_list("station__code", "metric__code", "observed_at", "value"))
        self.assertEqual(values(run.observations.all()), values(extended.observations.filter(observed_at__lt=START + timedelta(hours=24))))

    def test_missing_points_are_null_and_turbidity_scenario_has_peak(self):
        missing, _ = generate("missing", START, 24, seed=17)
        self.assertTrue(missing.observations.filter(value__isnull=True, quality_status="missing").exists())
        self.assertFalse(missing.observations.filter(value__isnull=False, quality_status="missing").exists())
        normal, _ = generate("normal", START, 24, seed=17)
        peak, _ = generate("turbidity", START, 24, seed=17)
        normal_max = max(normal.observations.filter(metric__code="turbidity").values_list("value", flat=True))
        peak_max = max(peak.observations.filter(metric__code="turbidity").values_list("value", flat=True))
        self.assertGreater(peak_max, normal_max + 60)

    def test_failed_run_is_recorded_and_partial_rows_rollback(self):
        from unittest.mock import patch
        with patch("ecology.simulation.Observation.objects.bulk_create", side_effect=RuntimeError("do not log this payload")):
            with self.assertRaises(RuntimeError):
                generate("normal", START, 2, seed=17)
        run = SimulationRun.objects.get()
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.error_code, "RuntimeError")
        self.assertEqual(Observation.objects.count(), 0)
        recovered, _ = generate("normal", START, 2, seed=17)
        self.assertEqual(recovered.status, "succeeded")
        self.assertEqual(recovered.counts, 26)

    def test_reject_unbounded_or_non_hourly_generation(self):
        for start, hours in [(START, 745), (START, 0), (START, 1.5), (START, True), (START + timedelta(minutes=1), 1), (START.replace(tzinfo=None), 1)]:
            with self.subTest(start=start, hours=hours), self.assertRaises(ValidationError):
                generate("normal", start, hours)

    def test_total_point_budget_and_disabled_source_are_enforced(self):
        source = DataSource.objects.get(code="demo-normal")
        source.is_active = False
        source.save()
        with self.assertRaises(ValidationError):
            generate("normal", START, 1)
        source.is_active = True
        source.save()
        base = Station.objects.get(code="demo-water-01")
        Station.objects.bulk_create([Station(region=base.region, place=base.place, water_body=base.water_body, code=f"additional-water-{i}", name=f"额外站{i}", kind="water") for i in range(14)])
        with self.assertRaises(ValidationError):
            generate("normal", START, 744)
        self.assertEqual(SimulationRun.objects.count(), 0)

    def test_invalid_scenario_parameters_fail_before_creating_batch(self):
        scenario = SimulationScenario.objects.get(code="missing")
        scenario.parameters = {"missing_every": 0}
        scenario.save()
        with self.assertRaises(ValidationError):
            generate("missing", START, 1)
        self.assertEqual(SimulationRun.objects.count(), 0)


class ImportTests(DemoDataTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.csv_path = Path(self.directory.name) / "observations.csv"
        self.source = DataSource.objects.create(code="history-fixture", name="测试历史数据", kind="dataset", license="测试生成")

    def write_rows(self, rows):
        with self.csv_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["station_code", "metric_code", "value", "unit", "observed_at", "source_code", "quality_status", "simulation_run_id"])
            writer.writeheader()
            for overrides in rows:
                row = {"station_code": "demo-water-01", "metric_code": "ph", "value": "7.2", "unit": "pH", "observed_at": "2020-01-01T08:00:00+08:00", "source_code": self.source.code, "quality_status": "valid", "simulation_run_id": ""}
                row.update(overrides)
                writer.writerow(row)

    def execute(self, **options):
        call_command("import_observations", str(self.csv_path), stdout=io.StringIO(), **options)

    def test_atomic_import_preserves_historical_time_and_is_idempotent(self):
        self.write_rows([{}, {"observed_at": "2020-01-01T09:00:00+08:00", "value": "", "quality_status": "missing"}])
        self.execute(dry_run=True)
        self.assertEqual(Observation.objects.count(), 0)
        self.execute()
        self.execute()
        self.assertEqual(Observation.objects.count(), 2)
        first = Observation.objects.order_by("observed_at").first()
        self.assertEqual(first.observed_at, datetime(2020, 1, 1, tzinfo=datetime_timezone.utc))
        self.assertGreater(first.ingested_at, first.observed_at)
        self.assertEqual(first.source.kind, "dataset")
        self.assertIsNone(Observation.objects.get(quality_status="missing").value)

    def test_bad_second_row_prevents_first_row_being_written(self):
        invalid_rows = [
            {"value": "NaN"}, {"value": "Inf"}, {"value": "-Infinity"}, {"unit": "mg/L"},
            {"value": "15"}, {"quality_status": "missing"}, {"observed_at": "2020-01-01T00:00:00"},
            {"station_code": "demo-air-01"}, {"source_code": "demo-normal"},
        ]
        for invalid in invalid_rows:
            with self.subTest(invalid=invalid):
                self.write_rows([{}, {"observed_at": "2020-01-01T09:00:00+08:00", **invalid}])
                with self.assertRaises(CommandError):
                    self.execute()
                self.assertEqual(Observation.objects.count(), 0)

    def test_conflicting_existing_value_rejects_whole_batch(self):
        self.write_rows([{}])
        self.execute()
        self.write_rows([{"observed_at": "2020-01-01T09:00:00+08:00"}, {"value": "7.5"}])
        with self.assertRaises(CommandError):
            self.execute()
        self.assertEqual(Observation.objects.count(), 1)
        self.assertEqual(Observation.objects.get().value, 7.2)

    def test_simulation_source_and_batch_must_match(self):
        run, _ = generate("normal", START, 2, seed=17)
        self.write_rows([{"source_code": "demo-missing", "simulation_run_id": str(run.pk), "observed_at": START.isoformat()}])
        with self.assertRaises(CommandError):
            self.execute()
        self.assertEqual(Observation.objects.count(), 26)


class PublicDataTests(DemoDataTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.normal, _ = generate("normal", START, 24, seed=17)
        self.missing, _ = generate("missing", START, 24, seed=17)

    def query(self, **params):
        view = ObservationList()
        view.request = Request(self.factory.get("/api/v1/observations/", params))
        return view.get_queryset()

    def test_default_query_selects_normal_and_one_run(self):
        later, _ = generate("normal", START, 24, seed=18)
        rows = list(self.query())
        self.assertEqual(len(rows), 24 * 13)
        self.assertEqual({row.simulation_run_id for row in rows}, {later.pk})
        missing = list(self.query(scenario="missing", metric="ph"))
        self.assertEqual({row.simulation_run_id for row in missing}, {self.missing.pk})

    def test_source_separation_and_invalid_mixed_source_requests(self):
        from rest_framework.exceptions import ValidationError as APIValidationError
        station = Station.objects.get(code="demo-water-01")
        metric = Metric.objects.get(code="ph")
        source = DataSource.objects.create(code="manual-one", name="人工测试", kind="manual")
        Observation.objects.create(station=station, metric=metric, source=source, value=8.8, observed_at=START, dedupe_key=observation_key(station, metric, source, START))
        self.assertEqual(self.query(source_type="manual").count(), 1)
        self.assertFalse(any(row.source.kind == "manual" for row in self.query()))
        second = DataSource.objects.create(code="manual-two", name="第二来源", kind="manual")
        Observation.objects.create(station=station, metric=metric, source=second, value=8.7, observed_at=START, dedupe_key=observation_key(station, metric, second, START))
        with self.assertRaises(APIValidationError):
            self.query(source_type="manual")
        self.assertEqual(self.query(source_type="manual", source="manual-one").count(), 1)
        with self.assertRaises(APIValidationError):
            self.query(source_type="dataset", source="manual-one")

    def test_time_and_point_limits_are_enforced(self):
        from rest_framework.exceptions import ValidationError as APIValidationError
        for params in [{"start": "2020-01-01T00:00:00Z", "end": "2021-01-01T00:00:00Z"}, {"limit": 1001}, {"limit": 0}, {"limit": "bad"}, {"start": "2026-09-15T00:00:00"}, {"source_type": "all"}]:
            with self.subTest(params=params), self.assertRaises(APIValidationError):
                self.query(**params)
        self.assertEqual(len(self.query(limit=10)), 10)

    def test_weather_air_and_alerts_are_explicit_about_simulation(self):
        for view in (EnvironmentalSummary, AirQuality):
            response = view.as_view()(self.factory.get("/api/v1/weather/"))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data["is_simulated"])
            self.assertEqual(response.data["source_type"], "simulation")
            self.assertTrue(response.data["metrics"])
        air = AirQuality.as_view()(self.factory.get("/api/v1/air-quality/"))
        self.assertIsNone(air.data["aqi"])
        alerts = WeatherAlerts.as_view()(self.factory.get("/api/v1/weather-alerts/"))
        self.assertEqual(alerts.data["status"], "not_connected")
        self.assertIn("不代表", alerts.data["notice"])


def _det(eval_cat, area_ratio=0.01):
    """构造一个检测框 dict 用于 assess() 测试。"""
    return {"eval_category": eval_cat, "conf": 0.8, "area_ratio": area_ratio}


class RuleV1Tests(TestCase):
    """评估规则引擎 RULE v1：扣分、等级、原因文本。"""

    def test_clean_image_is_excellent(self):
        from .rules import assess
        r = assess([], rule_version="v1")
        self.assertEqual(r["grade"], "优")
        self.assertEqual(r["score"], 100)

    def test_outfall_heavy_penalty(self):
        from .rules import assess
        r = assess([_det("outfall_discharge")], rule_version="v1")
        self.assertEqual(r["grade"], "良")
        self.assertEqual(r["score"], 75)

    def test_grade_boundaries(self):
        from .rules import assess
        self.assertEqual(assess([], "v1")["grade"], "优")
        self.assertEqual(assess([_det("outfall_discharge"),
                                 _det("bloom_blackwater", 0.1)], "v1")["grade"], "中")
        self.assertEqual(assess([_det("outfall_discharge"),
                                 _det("outfall_discharge"),
                                 _det("bloom_blackwater", 0.3),
                                 _det("bank_problem")], "v1")["grade"], "差")

    def test_causes_floating_plus_bank(self):
        from .rules import assess
        r = assess([_det("floating_debris")] * 4 + [_det("bank_problem")],
                    rule_version="v1")
        self.assertTrue(any("垃圾清运" in c["text"] for c in r["causes"]))

    def test_unknown_version_raises(self):
        from .rules import assess
        with self.assertRaises(ValueError):
            assess([], rule_version="vNonsense")

    def test_issues_aggregate_count_and_area(self):
        from .rules import assess
        r = assess([_det("floating_debris", 0.02),
                    _det("floating_debris", 0.03)], "v1")
        self.assertEqual(r["issues"]["floating_debris"]["count"], 2)
        self.assertAlmostEqual(r["issues"]["floating_debris"]["area_ratio"], 0.05)


class RuleSetModelTests(TestCase):
    """RuleSet 模型：版本唯一、单 active 约束、definition 校验。"""

    def test_create_v1_active(self):
        from .rules import RULE_V1
        from .models import RuleSet
        rs = RuleSet.objects.create(version="v1", definition=RULE_V1, is_active=True)
        self.assertEqual(str(rs), "RuleSet v1")
        self.assertTrue(rs.is_active)

    def test_only_one_active(self):
        from .rules import RULE_V1
        from .models import RuleSet
        RuleSet.objects.create(version="v1", definition=RULE_V1, is_active=True)
        with self.assertRaises(Exception):
            RuleSet.objects.create(version="v2", definition=RULE_V1, is_active=True)

    def test_definition_must_have_required_keys(self):
        from .models import RuleSet
        with self.assertRaises(ValidationError):
            RuleSet(version="bad", definition={"base": 100}).save()

    def test_db_rule_overrides_default(self):
        """若 DB 有匹配版本 RuleSet，assess() 优先使用 DB 定义。"""
        from .rules import assess
        from .models import RuleSet
        custom = {
            "base": 100,
            "floating_debris": {"count_steps": [(0, 0)], "area_steps": [(0.0, 0)]},
            "bloom_blackwater": {"area_steps": [(0.0, 0)]},
            "outfall_discharge": {"per_instance": 50, "cap": 100},
            "bank_problem": {"per_instance": 0, "cap": 0},
        }
        RuleSet.objects.create(version="custom1", definition=custom, is_active=False)
        r = assess([_det("outfall_discharge")], rule_version="custom1")
        self.assertEqual(r["score"], 50)  # 100 - 1*50 = 50


class GeoTests(TestCase):
    """定位 → 最近监测站 → 水体（Haversine 半径 2km）。"""

    @classmethod
    def setUpTestData(cls):
        cls.region = Region.objects.create(slug="geo-test-region", name="Geo 测试区域")
        cls.river_place = Place.objects.create(
            slug="geo-test-river", name="Geo 测试河", region=cls.region,
            kind=Place.Kind.RIVER, latitude=39.90, longitude=116.40,
            coordinate_system="WGS84", source_note="测试用经纬度。")
        cls.water = WaterBody.objects.create(place=cls.river_place)
        cls.station = Station.objects.create(
            code="geo-test-water-01", name="Geo 测试水站", region=cls.region,
            place=cls.river_place, water_body=cls.water, kind=Station.Kind.WATER)

    def test_nearest_station_within_radius(self):
        from .geo import match_water_body
        r = match_water_body(39.90, 116.40)
        self.assertIsNotNone(r)
        self.assertEqual(r["water_body_id"], self.water.id)
        self.assertEqual(r["station_id"], self.station.id)
        self.assertEqual(r["distance_m"], 0)

    def test_within_2km_returns_partial_distance(self):
        from .geo import match_water_body
        # 0.001 度约 111 米，仍在 2km 内
        r = match_water_body(39.901, 116.401)
        self.assertIsNotNone(r)
        self.assertLess(r["distance_m"], 200)

    def test_no_station_returns_none(self):
        from .geo import match_water_body
        # 远离测试站（海南三亚附近），超出 2km
        self.assertIsNone(match_water_body(18.30, 109.50))

    def test_inactive_station_ignored(self):
        from .geo import match_water_body
        self.station.is_active = False
        self.station.save()
        self.assertIsNone(match_water_body(39.90, 116.40))

    def test_station_without_water_body_returns_none(self):
        from .geo import match_water_body
        # 建一个没关联水体的 active 水站，距离更近
        no_water_place = Place.objects.create(
            slug="geo-no-water", name="无水体测试河", region=self.region,
            kind=Place.Kind.RIVER, latitude=39.905, longitude=116.405,
            coordinate_system="WGS84")
        Station.objects.create(
            code="geo-no-water-station", name="无水体水站", region=self.region,
            place=no_water_place, water_body=None, kind=Station.Kind.WATER)
        # 现有测试站离 39.90,116.40 更近且有水体，仍应匹配
        r = match_water_body(39.90, 116.40)
        self.assertEqual(r["water_body_id"], self.water.id)
        # 但靠近无水体站时返回 None
        self.assertIsNone(match_water_body(39.905, 116.405))


class AssessmentJobAPITests(TestCase):
    """河道评估任务 API：鉴权、入参校验、定位关联、详情契约。"""

    @classmethod
    def setUpTestData(cls):
        from accounts.models import User
        from assets.services import create_asset
        from django.core.files.uploadedfile import SimpleUploadedFile
        cls.user = User.objects.create_user(username="eco-tester", password="pw")
        cls.region = Region.objects.create(slug="eco-test-region", name="Eco 测试区域")
        cls.river_place = Place.objects.create(
            slug="eco-test-river", name="Eco 测试河", region=cls.region,
            kind=Place.Kind.RIVER, latitude=39.90, longitude=116.40,
            coordinate_system="WGS84", source_note="测试。")
        cls.water = WaterBody.objects.create(place=cls.river_place)
        cls.station = Station.objects.create(
            code="eco-test-water-01", name="Eco 测试水站", region=cls.region,
            place=cls.river_place, water_body=cls.water, kind=Station.Kind.WATER)
        # 用 PIL 生成最小 JPEG 上传
        from PIL import Image as _PILImage
        import io as _io
        buf = _io.BytesIO()
        _PILImage.new("RGB", (64, 64), (180, 90, 90)).save(buf, format="JPEG", quality=80)
        cls.asset = create_asset(cls.user, SimpleUploadedFile("a.jpg", buf.getvalue(), "image/jpeg"), "recognition")

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_create_requires_auth(self):
        from accounts.models import User
        anon = User.objects.create_user(username="eco-anon", password="pw")
        c = APIClient()  # 不 force_authenticate
        r = c.post("/api/v1/assessment-jobs/", {"asset_id": str(self.asset.id),
                                                "latitude": 39.90, "longitude": 116.40})
        self.assertEqual(r.status_code, 401)

    def test_create_requires_lat_lng(self):
        r = self.client.post("/api/v1/assessment-jobs/", {"asset_id": str(self.asset.id)})
        self.assertEqual(r.status_code, 400)

    def test_create_succeeds_and_links_water_body(self):
        r = self.client.post("/api/v1/assessment-jobs/",
                             {"asset_id": str(self.asset.id),
                              "latitude": 39.90, "longitude": 116.40})
        self.assertEqual(r.status_code, 201)
        body = r.json()["data"]
        self.assertEqual(body["status"], "queued")
        self.assertEqual(body["water_body_id"], str(self.water.id))
        self.assertEqual(body["station_id"], str(self.station.id))
        self.assertEqual(body["rule_version"], "v1")
        self.assertIn("disclaimer", body)
        self.assertIn("平台演示评分", body["disclaimer"])

    def test_create_far_from_station_keeps_null_water_body(self):
        r = self.client.post("/api/v1/assessment-jobs/",
                             {"asset_id": str(self.asset.id),
                              "latitude": 18.30, "longitude": 109.50})
        self.assertEqual(r.status_code, 201)
        body = r.json()["data"]
        self.assertIsNone(body["water_body_id"])
        self.assertIsNone(body["station_id"])

    def test_detail_contract(self):
        from datetime import timedelta
        from django.utils import timezone
        job = AssessmentJob.objects.create(
            owner=self.user, asset=self.asset,
            latitude=39.90, longitude=116.40, coordinate_system="WGS84",
            water_body=self.water, station=self.station,
            rule_version="v1", status="succeeded",
            detections=[{"eval_category": "outfall_discharge", "conf": 0.9, "area_ratio": 0.02}],
            score=75, grade="良", causes=[{"rule": "outfall", "text": "检出疑似排污口"}],
            expires_at=timezone.now() + timedelta(days=30))
        r = self.client.get(f"/api/v1/assessment-jobs/{job.id}/")
        self.assertEqual(r.status_code, 200)
        body = r.json()["data"]
        for key in ("status", "detections", "score", "grade", "causes",
                    "rule_version", "water_body_id", "disclaimer"):
            self.assertIn(key, body)
        self.assertEqual(body["score"], 75)
        self.assertEqual(body["grade"], "良")

    def test_list_filter_by_water_body(self):
        from datetime import timedelta
        from django.utils import timezone
        AssessmentJob.objects.create(
            owner=self.user, asset=self.asset,
            latitude=39.90, longitude=116.40, water_body=self.water,
            rule_version="v1", expires_at=timezone.now() + timedelta(days=30))
        # 另一任务不关联 water_body
        AssessmentJob.objects.create(
            owner=self.user, asset=self.asset,
            latitude=39.90, longitude=116.40,
            rule_version="v1", expires_at=timezone.now() + timedelta(days=30))
        r = self.client.get(f"/api/v1/assessment-jobs/?water_body={self.water.id}")
        self.assertEqual(r.status_code, 200)
        body = r.json()["data"]
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["water_body_id"], str(self.water.id))

    def test_delete_cascades_asset(self):
        from datetime import timedelta
        from django.utils import timezone
        from assets.models import Asset
        job = AssessmentJob.objects.create(
            owner=self.user, asset=self.asset,
            latitude=39.90, longitude=116.40, water_body=self.water,
            rule_version="v1", expires_at=timezone.now() + timedelta(days=30))
        asset_id = self.asset.id
        r = self.client.delete(f"/api/v1/assessment-jobs/{job.id}/")
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Asset.objects.filter(pk=asset_id).exists())


class AssessmentWorkerTests(TestCase):
    """评估工作进程：检测+评估管道端到端（mock ONNX，验证落库契约）。"""

    @classmethod
    def setUpTestData(cls):
        from accounts.models import User
        from assets.services import create_asset
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image as _PILImage
        import io as _io
        cls.user = User.objects.create_user(username="worker-tester", password="pw")
        buf = _io.BytesIO()
        _PILImage.new("RGB", (640, 640), (90, 90, 180)).save(buf, format="JPEG", quality=80)
        cls.asset = create_asset(cls.user, SimpleUploadedFile("w.jpg", buf.getvalue(), "image/jpeg"), "recognition")

    def _make_queued_job(self, rule_version="v1"):
        """创建一个 queued AssessmentJob，model_snapshot 包含可识别的标签映射。"""
        from datetime import timedelta
        from django.utils import timezone
        snapshot = {
            "id": "test-detection-id",
            "name": "test-detection-model",
            "version": "test-v1",
            "artifact": "fake.onnx",
            "sha256": "0" * 64,
            "labels": [
                {"id": 0, "name": "bottle", "eval_category": "floating_debris"},
                {"id": 5, "name": "outfall", "eval_category": "outfall_discharge"},
            ],
            "threshold": 0.5,
        }
        return AssessmentJob.objects.create(
            owner=self.user, asset=self.asset,
            model_snapshot=snapshot, status="queued",
            latitude=39.90, longitude=116.40,
            rule_version=rule_version,
            expires_at=timezone.now() + timedelta(days=30))

    def test_job_pipeline_produces_grade(self):
        from unittest.mock import patch
        from ecology.assessment_worker import process_one
        job = self._make_queued_job()
        fake_result = {
            "boxes": [
                {"class_id": 5, "conf": 0.9, "x1": 0, "y1": 0, "x2": 100, "y2": 100},
            ],
            "image_width": 640, "image_height": 640,
        }
        with patch("ecology.detection.detect", return_value=fake_result):
            self.assertTrue(process_one())
        job.refresh_from_db()
        self.assertEqual(job.status, "succeeded")
        self.assertEqual(len(job.detections), 1)
        self.assertEqual(job.detections[0]["eval_category"], "outfall_discharge")
        self.assertIsNotNone(job.grade)
        self.assertEqual(job.rule_version, "v1")

    def test_two_outfalls_yield_grade_liang(self):
        """2 个 outfall_discharge → score 50 → grade 中。"""
        from unittest.mock import patch
        from ecology.assessment_worker import process_one
        job = self._make_queued_job()
        fake_result = {
            "boxes": [
                {"class_id": 5, "conf": 0.9, "x1": 0, "y1": 0, "x2": 100, "y2": 100},
                {"class_id": 5, "conf": 0.85, "x1": 200, "y1": 200, "x2": 300, "y2": 300},
            ],
            "image_width": 640, "image_height": 640,
        }
        with patch("ecology.detection.detect", return_value=fake_result):
            process_one()
        job.refresh_from_db()
        self.assertEqual(job.status, "succeeded")
        self.assertEqual(job.score, 60)
        self.assertEqual(job.grade, "中")

    def test_clean_image_yields_grade_you(self):
        from unittest.mock import patch
        from ecology.assessment_worker import process_one
        job = self._make_queued_job()
        fake_result = {"boxes": [], "image_width": 640, "image_height": 640}
        with patch("ecology.detection.detect", return_value=fake_result):
            process_one()
        job.refresh_from_db()
        self.assertEqual(job.status, "succeeded")
        self.assertEqual(job.score, 100)
        self.assertEqual(job.grade, "优")
        self.assertEqual(job.detections, [])

    def test_inference_failure_marks_failed_no_fake_result(self):
        from unittest.mock import patch
        from ecology.assessment_worker import process_one
        job = self._make_queued_job()
        with patch("ecology.detection.detect", side_effect=RuntimeError("INFERENCE_FAILED")):
            process_one()
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.error_code, "INFERENCE_FAILED")
        self.assertEqual(job.detections, [])
        self.assertIsNone(job.score)

    def test_active_rule_set_persists_on_job(self):
        from unittest.mock import patch
        from ecology.rules import RULE_V1
        from ecology.assessment_worker import process_one
        rs = RuleSet.objects.create(version="v1", definition=RULE_V1, is_active=True)
        job = self._make_queued_job(rule_version="v1")
        fake_result = {
            "boxes": [{"class_id": 5, "conf": 0.9, "x1": 0, "y1": 0, "x2": 100, "y2": 100}],
            "image_width": 640, "image_height": 640,
        }
        with patch("ecology.detection.detect", return_value=fake_result):
            process_one()
        job.refresh_from_db()
        self.assertEqual(job.status, "succeeded")
        self.assertIsNotNone(job.rule_set_id)
        self.assertEqual(job.rule_set_id, rs.id)
