import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connection, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from common.models import AuditLog
from .maintenance import MaintenanceError, create_preview, execute_preview, lock_policy
from .models import (DataSource, Observation, Region, SimulationCleanupPreview,
                     SimulationRetentionPolicy, SimulationRun, Station)
from .simulation import generate


def old_batches():
    call_command("seed_demo", no_observations=True, stdout=io.StringIO())
    start = (timezone.now() - timedelta(days=60)).replace(minute=0, second=0, microsecond=0)
    runs = []
    for day in range(5):
        run, _ = generate("normal", start + timedelta(days=day), 1)
        SimulationRun.objects.filter(pk=run.pk).update(created_at=run.end, completed_at=run.end)
        run.refresh_from_db()
        runs.append(run)
    return runs


class MaintenanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.runs = old_batches()
        cls.admin = get_user_model().objects.create_superuser(username="maintenance", password="only-test-password")

    def test_preview_is_read_only_and_preserves_last_three_per_source_scenario(self):
        before = Observation.objects.count()
        plan = create_preview(self.admin)
        self.assertEqual(plan["batch_count"], 2)
        self.assertEqual(plan["observation_count"], 26)
        self.assertEqual(Observation.objects.count(), before)
        self.assertEqual({row["id"] for row in plan["protected"]}, {str(run.pk) for run in self.runs[2:]})
        self.assertTrue(all("latest" in row["reasons"] for row in plan["protected"]))
        result = execute_preview(plan["token"], self.admin)
        self.assertEqual(result, {"batch_count": 2, "observation_count": 26})
        self.assertEqual(SimulationRun.objects.count(), 3)
        self.assertEqual(Observation.objects.count(), 39)
        self.assertEqual(AuditLog.objects.get(event="simulation.cleanup.execute").details["count"], 26)
        with self.assertRaises(MaintenanceError) as context:
            execute_preview(plan["token"], self.admin)
        self.assertEqual(context.exception.code, "invalid_preview")

    def test_latest_observation_range_is_protected_even_if_created_long_ago(self):
        Observation.objects.filter(simulation_run=self.runs[0]).update(observed_at=self.runs[-1].end)
        SimulationRun.objects.filter(pk=self.runs[0].pk).update(end=self.runs[-1].end + timedelta(days=1))
        plan = create_preview(self.admin)
        protected = next(row for row in plan["protected"] if row["id"] == str(self.runs[0].pk))
        self.assertIn("latest_observation", protected["reasons"])

    def test_station_missing_from_newer_runs_keeps_its_actual_latest_batch(self):
        station = Station.objects.get(code="demo-water-01")
        for run in self.runs[1:]:
            Observation.objects.filter(simulation_run=run, station=station).delete()
            SimulationRun.objects.filter(pk=run.pk).update(counts=run.observations.count())
        plan = create_preview(self.admin)
        item = next(row for row in plan["protected"] if row["id"] == str(self.runs[0].pk))
        self.assertIn("latest_station", item["reasons"])
        self.assertEqual(plan["batch_count"], 1)

    def test_running_unknown_and_recent_batches_are_never_candidates(self):
        SimulationRun.objects.filter(pk=self.runs[0].pk).update(status="running")
        SimulationRun.objects.filter(pk=self.runs[1].pk).update(status="pending")
        plan = create_preview(self.admin)
        self.assertEqual(plan["batch_count"], 0)
        self.assertTrue(all("active" in row["reasons"] for row in plan["protected"] if row["id"] in {str(r.pk) for r in self.runs[:2]}))
        SimulationRun.objects.filter(pk=self.runs[0].pk).update(status="failed", completed_at=timezone.now())
        plan = create_preview(self.admin)
        self.assertIn("recent", next(row for row in plan["protected"] if row["id"] == str(self.runs[0].pk))["reasons"])

    def test_exact_retention_boundary_is_protected_then_expires(self):
        now = timezone.now()
        cutoff = now - timedelta(days=30)
        SimulationRun.objects.filter(pk=self.runs[0].pk).update(status="failed", end=cutoff)
        with patch("ecology.maintenance.timezone.now", return_value=now):
            plan = create_preview(self.admin)
        item = next(row for row in plan["protected"] if row["id"] == str(self.runs[0].pk))
        self.assertIn("recent", item["reasons"])
        with patch("ecology.maintenance.timezone.now", return_value=now + timedelta(microseconds=1)):
            plan = create_preview(self.admin)
        self.assertIn(str(self.runs[0].pk), [row["id"] for row in plan["candidates"]])

    def test_wrong_actor_tampered_expired_and_reused_tokens_fail(self):
        token = create_preview(self.admin)["token"]
        with self.assertRaises(MaintenanceError):
            execute_preview(token)
        with self.assertRaises(MaintenanceError):
            execute_preview(token + "broken", self.admin)
        SimulationCleanupPreview.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(MaintenanceError):
            execute_preview(token, self.admin)
        self.assertEqual(SimulationRun.objects.count(), 5)

    def test_policy_or_batch_or_value_changes_invalidate_preview(self):
        for model, kwargs in [(SimulationRetentionPolicy, {"retain_days": 31}),
                              (SimulationRun, {"error_code": "changed"}),
                              (Observation, {"value": 1})]:
            with self.subTest(model=model.__name__):
                token = create_preview(self.admin)["token"]
                model.objects.all().update(**kwargs)
                with self.assertRaises(MaintenanceError) as context:
                    execute_preview(token, self.admin)
                self.assertEqual(context.exception.code, "stale_preview")
        self.assertEqual(Observation.objects.count(), 65)

    def test_real_imported_and_mislinked_observations_cannot_be_cleaned(self):
        real = DataSource.objects.create(code="real-test", name="真实来源", kind="api")
        base = self.runs[0].observations.first()
        Observation.objects.filter(pk=base.pk).update(source=real)
        imported = Observation.objects.create(station=base.station, metric=base.metric, source=real,
            observed_at=base.observed_at, value=base.value, dedupe_key="real-import-outside-run")
        plan = create_preview(self.admin)
        item = next(row for row in plan["protected"] if row["id"] == str(self.runs[0].pk))
        self.assertIn("unsafe_scope", item["reasons"])
        execute_preview(plan["token"], self.admin)
        self.assertTrue(Observation.objects.filter(pk__in=[base.pk, imported.pk]).count() == 2)
        self.assertTrue(SimulationRun.objects.filter(pk=self.runs[0].pk).exists())

    def test_invalid_source_or_non_demo_station_or_count_is_protected(self):
        DataSource.objects.filter(pk=self.runs[0].source_id).update(kind="api")
        plan = create_preview(self.admin)
        self.assertEqual(plan["batch_count"], 0)
        self.assertTrue(all("unsafe_source" in row["reasons"] for row in plan["protected"]))
        DataSource.objects.filter(pk=self.runs[0].source_id).update(kind="simulation")
        Region.objects.filter(slug="demo-campus").update(is_demo=False)
        self.assertEqual(create_preview(self.admin)["batch_count"], 0)
        Region.objects.filter(slug="demo-campus").update(is_demo=True)
        SimulationRun.objects.filter(pk=self.runs[0].pk).update(counts=999)
        plan = create_preview(self.admin)
        item = next(row for row in plan["protected"] if row["id"] == str(self.runs[0].pk))
        self.assertIn("count_mismatch", item["reasons"])

    def test_cross_region_and_out_of_range_observations_protect_whole_batch(self):
        base = self.runs[0].observations.filter(station__place__isnull=False).first()
        other = Region.objects.create(slug="maintenance-other", name="其他区")
        Station.objects.filter(pk=base.station_id).update(region=other)
        Observation.objects.filter(simulation_run=self.runs[1]).update(observed_at=self.runs[1].end)
        plan = create_preview(self.admin)
        self.assertEqual(plan["batch_count"], 0)

    def test_failure_rolls_back_observation_deletion_and_preview_consumption(self):
        plan = create_preview(self.admin)
        with patch("ecology.maintenance.audit", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                execute_preview(plan["token"], self.admin)
        self.assertEqual(SimulationRun.objects.count(), 5)
        self.assertEqual(Observation.objects.count(), 65)
        self.assertIsNone(SimulationCleanupPreview.objects.get().consumed_at)
        execute_preview(plan["token"], self.admin)
        self.assertEqual(SimulationRun.objects.count(), 3)

    def test_retention_is_per_source_and_scenario_and_policy_minimum(self):
        missing, _ = generate("missing", self.runs[0].start, 1)
        SimulationRun.objects.filter(pk=missing.pk).update(created_at=missing.end, completed_at=missing.end)
        policy = SimulationRetentionPolicy.objects.get()
        policy.keep_successful = 1
        policy.save()
        plan = create_preview(self.admin)
        self.assertEqual(plan["batch_count"], 4)
        self.assertIn(str(missing.pk), [row["id"] for row in plan["protected"]])
        policy.retain_days = 29
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            policy.save()
        policy.retain_days = 30
        policy.keep_successful = 0
        with self.assertRaises(ValidationError):
            policy.save()

    def test_command_defaults_to_dry_run_and_requires_matching_execute_token(self):
        output = io.StringIO()
        call_command("maintain_simulation", as_json=True, stdout=output)
        plan = json.loads(output.getvalue())
        self.assertEqual(SimulationRun.objects.count(), 5)
        with self.assertRaises(CommandError):
            call_command("maintain_simulation", execute=True, stdout=io.StringIO())
        with self.assertRaises(CommandError):
            call_command("maintain_simulation", token=plan["token"], stdout=io.StringIO())
        call_command("maintain_simulation", execute=True, token=plan["token"], stdout=io.StringIO())
        self.assertEqual(SimulationRun.objects.count(), 3)
        with self.assertRaises(CommandError):
            call_command("maintain_simulation", execute=True, token=plan["token"], stdout=io.StringIO())

    def test_admin_permissions_csrf_and_explicit_confirmation(self):
        path = reverse("admin:ecology_simulationrun_maintenance")
        staff = get_user_model().objects.create_user(username="read-only-maintenance", password="only-test-password", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(path).status_code, 403)
        staff.user_permissions.add(*Permission.objects.filter(codename__in=["view_simulationrun", "maintain_simulation"]))
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(SimulationCleanupPreview.objects.count(), 0)
        client = Client(enforce_csrf_checks=True)
        client.force_login(staff)
        self.assertEqual(client.post(path, {"action": "preview"}).status_code, 403)
        client.get(path)
        csrf = client.cookies["csrftoken"].value
        response = client.post(path, {"action": "preview", "csrfmiddlewaretoken": csrf})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 个候选批次 / 26 条实际观测")
        token = response.context["plan"]["token"]
        self.assertEqual(client.post(path, {"action": "execute", "token": token, "csrfmiddlewaretoken": csrf}).status_code, 400)
        self.assertEqual(SimulationRun.objects.count(), 5)
        self.assertEqual(client.post(path, {"action": "execute", "token": token, "confirm": "on", "csrfmiddlewaretoken": csrf}).status_code, 302)
        self.assertEqual(SimulationRun.objects.count(), 3)

    def test_admin_batch_list_reports_actual_count_without_edit_delete_bypass(self):
        self.client.force_login(self.admin)
        SimulationRun.objects.filter(pk=self.runs[0].pk).update(counts=999)
        response = self.client.get(reverse("admin:ecology_simulationrun_changelist"))
        self.assertContains(response, "实际观测数")
        self.assertEqual(self.client.get(reverse("admin:ecology_simulationrun_changelist"), {"q": "normal"}).status_code, 200)
        self.assertContains(response, "保留策略与清理预览")
        self.assertEqual(response.context["cl"].result_list[0].actual_observations, 13)
        self.assertEqual(self.client.post(reverse("admin:ecology_simulationrun_delete", args=[self.runs[0].pk]), {"post": "yes"}).status_code, 403)
        obs = Observation.objects.first()
        self.assertEqual(self.client.post(reverse("admin:ecology_observation_delete", args=[obs.pk]), {"post": "yes"}).status_code, 403)


class MaintenanceConcurrencyTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Row-lock concurrency is verified with PostgreSQL")
        self.runs = old_batches()

    def test_only_one_concurrent_execution_consumes_preview(self):
        token = create_preview()["token"]
        def run():
            close_old_connections()
            try:
                execute_preview(token)
                return "deleted"
            except MaintenanceError as exc:
                return exc.code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: run(), range(2)))
        self.assertEqual(sorted(results), ["deleted", "invalid_preview"])
        self.assertEqual(SimulationRun.objects.count(), 3)
        self.assertEqual(AuditLog.objects.filter(event="simulation.cleanup.execute").count(), 1)

    def test_generator_waits_for_maintenance_lock_and_invalidates_older_preview(self):
        token = create_preview()["token"]
        entered = Event()
        done = Event()
        start = timezone.now().replace(minute=0, second=0, microsecond=0)
        def run():
            close_old_connections()
            try:
                return generate("normal", start, 1)
            finally:
                done.set()
                close_old_connections()
        def observed_lock():
            entered.set()
            return lock_policy()
        with patch("ecology.simulation.lock_policy", side_effect=observed_lock), ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                lock_policy()
                future = pool.submit(run)
                self.assertTrue(entered.wait(5))
                self.assertFalse(done.wait(0.2))
                self.assertEqual(SimulationRun.objects.count(), 5)
            future.result(timeout=10)
        with self.assertRaises(MaintenanceError) as context:
            execute_preview(token)
        self.assertEqual(context.exception.code, "stale_preview")
        self.assertEqual(SimulationRun.objects.count(), 6)


    def test_generator_rechecks_region_after_waiting_for_shared_lock(self):
        entered = Event()
        start = timezone.now().replace(minute=0, second=0, microsecond=0)
        def observed_lock():
            entered.set()
            return lock_policy()
        def run():
            close_old_connections()
            try:
                return generate("normal", start, 1)
            finally:
                close_old_connections()
        from django.core.exceptions import ValidationError
        with patch("ecology.simulation.lock_policy", side_effect=observed_lock), ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                lock_policy()
                future = pool.submit(run)
                self.assertTrue(entered.wait(5))
                Region.objects.filter(slug="demo-campus").update(is_demo=False)
            with self.assertRaises(ValidationError):
                future.result(timeout=10)
        self.assertEqual(SimulationRun.objects.count(), 5)
        self.assertEqual(Observation.objects.count(), 65)

    def test_generator_holds_source_lock_through_observation_write(self):
        inside_write, release_write = Event(), Event()
        update_started, update_done = Event(), Event()
        original_bulk = Observation.objects.bulk_create
        start = timezone.now().replace(minute=0, second=0, microsecond=0)
        def paused_bulk(rows, **kwargs):
            inside_write.set()
            if not release_write.wait(5):
                raise RuntimeError("test coordination timed out")
            return original_bulk(rows, **kwargs)
        def generate_thread():
            close_old_connections()
            try:
                return generate("normal", start, 1)
            finally:
                close_old_connections()
        def update_thread():
            close_old_connections()
            update_started.set()
            try:
                DataSource.objects.filter(code="demo-normal").update(is_active=False)
                update_done.set()
            finally:
                close_old_connections()
        with patch("ecology.simulation.Observation.objects.bulk_create", side_effect=paused_bulk), ThreadPoolExecutor(max_workers=2) as pool:
            generation = pool.submit(generate_thread)
            try:
                self.assertTrue(inside_write.wait(5))
                updating = pool.submit(update_thread)
                self.assertTrue(update_started.wait(5))
                self.assertFalse(update_done.wait(0.2))
            finally:
                release_write.set()
            run, created = generation.result(timeout=10)
            updating.result(timeout=10)
        self.assertTrue(created)
        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.observations.count(), 13)
        self.assertFalse(DataSource.objects.get(code="demo-normal").is_active)
