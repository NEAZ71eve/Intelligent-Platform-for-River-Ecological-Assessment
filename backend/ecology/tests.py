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
from rest_framework.test import APIRequestFactory

from .models import DataSource, MapLayout, Metric, Observation, Place, Region, SimulationRun, SimulationScenario, Station, WaterBody
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
