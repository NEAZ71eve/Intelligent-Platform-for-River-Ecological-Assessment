#!/usr/bin/env python3
"""Short, bounded internal concurrency sample; NOT the M4-05 30-minute test.

Run as hyhq with production environment variables loaded. Creates six temporary
passwordless accounts, then removes precisely their sessions, records and files.
Only http://127.0.0.1:18080 is supported, with trusted deployment proxy headers.
This does not verify public HTTPS, WeChat login, or image recognition accuracy.
"""

import argparse
from collections import Counter
import importlib.util
import json
import logging
import math
import os
from pathlib import Path
import pwd
import signal
import sys
import threading
import time
import uuid


spec = importlib.util.spec_from_file_location(
    "production_smoke", Path(__file__).with_name("production-smoke.py"))
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)
ENDPOINTS = ("dashboard/", "places/", "weather/", "air-quality/", "water-bodies/")
REQUEST_TIMEOUT = 3
AI_POLL_TIMEOUT = 20


def percentiles(samples):
    """Nearest-rank milliseconds, including failed HTTP attempt durations."""
    values = sorted(samples)
    if not values:
        return {"p50_ms": None, "p95_ms": None, "max_ms": None}
    return {"p50_ms": round(values[math.ceil(len(values) * .50) - 1], 1),
            "p95_ms": round(values[math.ceil(len(values) * .95) - 1], 1),
            "max_ms": round(values[-1], 1)}


def memory_snapshot(path=Path("/proc/meminfo")):
    values = {}
    for line in path.read_text().splitlines():
        name, value = line.split(":", 1)
        if name in {"MemAvailable", "SwapTotal", "SwapFree"}:
            values[name] = int(value.split()[0])
    return values["MemAvailable"], values["SwapTotal"] - values["SwapFree"]


def safe_failure(error):
    # Only module-defined fixed labels are emitted; never arbitrary exceptions.
    return str(error) if isinstance(error, smoke.SmokeFailure) else "UNEXPECTED_LOCAL_ERROR"


class BoundedAPI(smoke.API):
    def __init__(self, deadline):
        super().__init__("http://127.0.0.1:18080", trusted_loopback=True)
        self.deadline = deadline

    def request(self, method, path, token=None, body=None, content_type=None,
                expected=(200,), timeout=REQUEST_TIMEOUT):
        remaining = self.deadline - time.monotonic()
        smoke.require(remaining > 0, "HTTP_DEADLINE_EXCEEDED")
        return super().request(method, path, token, body, content_type, expected,
                               min(timeout, REQUEST_TIMEOUT, remaining))


def browse_loop(index, token, deadline, stop, result, api_factory=BoundedAPI):
    api = api_factory(deadline + REQUEST_TIMEOUT)
    next_request = time.monotonic()
    while not stop.is_set() and time.monotonic() < deadline:
        if stop.wait(max(0, min(next_request, deadline) - time.monotonic())):
            break
        if time.monotonic() >= deadline:
            break
        started = time.monotonic()
        endpoint = ENDPOINTS[(index + result["attempts"]) % len(ENDPOINTS)]
        result["attempts"] += 1
        try:
            api.json("GET", endpoint, token)
            result["succeeded"] += 1
        except Exception as error:
            result["errors"][safe_failure(error)] += 1
        finally:
            result["latencies"].append((time.monotonic() - started) * 1000)
        # Slow requests never trigger a burst of catch-up requests.
        next_request = max(next_request + 1, time.monotonic())


def ai_loop(token, images, deadline, stop, result, api_factory=BoundedAPI, remember_files=None):
    api = api_factory(deadline + 30)
    next_job = time.monotonic()
    while not stop.is_set() and time.monotonic() < deadline:
        if stop.wait(max(0, min(next_job, deadline) - time.monotonic())):
            break
        if time.monotonic() >= deadline:
            break
        index = result["attempts"] % 2
        endpoint = ("recognition-jobs/", "assessment-jobs/")[index]
        sample = {"kind": ("flower", "river")[index], "status": "failed"}
        result["attempts"] += 1
        started = time.monotonic()
        job = None
        try:
            asset = api.upload(token, images[index])
            if remember_files is not None:
                remember_files()
            job = api.json("POST", endpoint, token, {"asset_id": asset["id"]}, (201,))
            smoke.require(job.get("asset_id") == asset["id"], "INCORRECT_JOB_ASSET")
            poll_deadline = min(time.monotonic() + AI_POLL_TIMEOUT, deadline + 25)
            while job.get("status") in {"queued", "running"}:
                remaining = poll_deadline - time.monotonic()
                smoke.require(remaining > 0, "AI_POLL_DEADLINE_EXCEEDED")
                # A running task is drained even when the sampling period ends.
                job = api.json("GET", endpoint + job["id"] + "/", token, timeout=remaining)
                if job.get("status") in {"queued", "running"}:
                    time.sleep(min(.75, max(0, poll_deadline - time.monotonic())))
            smoke.require(job.get("status") == "succeeded", "WORKER_JOB_FAILED")
            (smoke.check_recognition, smoke.check_assessment)[index](job)
            duration = job.get("duration_ms")
            smoke.require(smoke.finite_number(duration) and duration >= 0, "INVALID_WORKER_DURATION")
            sample.update(status="passed", worker_duration_ms=duration)
            sample["end_to_end_ms"] = round((time.monotonic() - started) * 1000, 1)
        except Exception as error:
            result["errors"][safe_failure(error)] += 1
            sample["failure"] = safe_failure(error)
        finally:
            # Exact ownership is also checked and cleaned through Django at exit,
            # covering a lost upload/create response and unfinished worker jobs.
            if job and job.get("id"):
                try:
                    api.json("DELETE", endpoint + job["id"] + "/", token, expected=(204,))
                except Exception as error:
                    result["errors"][safe_failure(error)] += 1
                    sample.update(status="failed", cleanup_failure=safe_failure(error))
            sample["iteration_ms"] = round((time.monotonic() - started) * 1000, 1)
            result["samples"].append(sample)
        next_job = max(started + 10, time.monotonic())


def sample_memory(stop, result):
    while True:
        try:
            available, swap = memory_snapshot()
            result["samples"] += 1
            result["mem_available_min_kib"] = min(result["mem_available_min_kib"], available)
            result["swap_used_max_kib"] = max(result["swap_used_max_kib"], swap)
        except Exception:
            result["errors"] += 1
        if stop.wait(.5):
            break


def run(args, report):
    smoke.origin_from_url(args.base_url, trusted_loopback=True)
    smoke.require(1 <= args.duration <= 180, "DURATION_MUST_BE_1_TO_180_SECONDS")
    smoke.require(os.environ.get("ENV") == "production", "PRODUCTION_ENVIRONMENT_REQUIRED")
    smoke.require(pwd.getpwuid(os.geteuid()).pw_name == "hyhq", "RUN_AS_HYHQ_REQUIRED")
    images = []
    for filename in (args.flower_image, args.river_image):
        with Path(filename).open("rb") as source:
            content = source.read(smoke.MAX_UPLOAD + 1)
        smoke.require(0 < len(content) <= smoke.MAX_UPLOAD, "FIXTURE_SIZE_OUT_OF_RANGE")
        images.append(content)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    django.setup()
    logging.disable(logging.CRITICAL)
    from django.conf import settings
    from django.db import connections
    from accounts.models import AuthSession, User
    from accounts.services import issue_session
    from assets.models import Asset
    from assessments.models import AssessmentJob
    from recognition.models import RecognitionJob
    smoke.require(settings.ENV == "production" and not settings.DEBUG and not settings.ALLOW_DEV_AUTH,
                  "PRODUCTION_SETTINGS_REQUIRED")

    users, tokens, saved_files, threads = [], [], {}, []
    stop, memory_stop = threading.Event(), threading.Event()
    browsers = [{"attempts": 0, "succeeded": 0, "errors": Counter(), "latencies": []} for _ in range(5)]
    ai = {"attempts": 0, "errors": Counter(), "samples": []}
    memory = {"samples": 0, "errors": 0, "mem_available_min_kib": math.inf, "swap_used_max_kib": 0}
    memory_thread = None

    def remember_asset_files():
        # Preserve exact storage names before the API deletes each task. This
        # also lets final cleanup retry storage failures after DB-row deletion.
        # Only the AI thread calls this while sampling; main reads after joining.
        try:
            for asset in Asset.objects.filter(owner_id__in=[pk for pk, _ in users]):
                for field in (asset.original, asset.thumbnail):
                    if field.name:
                        saved_files[field.name] = field.storage
        finally:
            connections.close_all()

    try:
        setup_api = BoundedAPI(time.monotonic() + 30)
        health = setup_api.json("GET", "health/")
        smoke.require(health.get("status") == "ok" and health.get("dev_auth_enabled") is False,
                      "PRODUCTION_HEALTH_REQUIRED")
        smoke.require(health.get("features", {}).get("recognition") is True
                      and health.get("features", {}).get("assessment") is True, "BOTH_MODELS_REQUIRED")
        for _ in range(6):
            pk, username = uuid.uuid4(), "load-smoke-" + uuid.uuid4().hex
            users.append((pk, username))
            user = User.objects.create_user(id=pk, username=username, password=None)
            token, _ = issue_session(user)
            tokens.append(token)
            profile = setup_api.json("GET", "me/", token)
            smoke.require(profile.get("id") == str(pk), "LOCAL_DB_AND_API_ACCOUNT_MISMATCH")
        smoke.require(args.duration + 45 < args.hard_deadline - time.monotonic(),
                      "INSUFFICIENT_TIME_FOR_FULL_SAMPLE_AND_CLEANUP")
        started = time.monotonic()
        deadline = started + args.duration
        for index in range(5):
            threads.append(threading.Thread(target=browse_loop,
                           args=(index, tokens[index], deadline, stop, browsers[index]), daemon=True))
        threads.append(threading.Thread(target=ai_loop,
                       args=(tokens[5], images, deadline, stop, ai),
                       kwargs={"remember_files": remember_asset_files}, daemon=True))
        memory_thread = threading.Thread(target=sample_memory, args=(memory_stop, memory), daemon=True)
        memory_thread.start()
        for thread in threads:
            thread.start()
        stop.wait(max(0, deadline - time.monotonic()))
        report["sampling_elapsed_ms"] = round((time.monotonic() - started) * 1000)
    finally:
        stop.set()
        # Allow already submitted AI work to finish and delete its own records.
        # The hard timer also covers cleanup. Only the AI thread briefly queries
        # its own assets to preserve file names, closing its DB connection first.
        signal.setitimer(signal.ITIMER_REAL,
                         min(55, max(.001, args.hard_deadline - time.monotonic())))
        join_deadline = time.monotonic() + 32
        for thread in threads:
            if thread.ident is not None:
                thread.join(max(0, join_deadline - time.monotonic()))
        memory_stop.set()
        if memory_thread is not None:
            memory_thread.join(1)
        report["threads_drained"] = not any(thread.is_alive() for thread in threads)
        try:
            ids = [pk for pk, _ in users]
            for asset in Asset.objects.filter(owner_id__in=ids):
                for field in (asset.original, asset.thumbnail):
                    if field.name:
                        saved_files[field.name] = field.storage
            for pk, username in users:
                User.objects.filter(pk=pk, username=username).delete()
            for name, storage in saved_files.items():
                if storage.exists(name):
                    storage.delete(name)
            smoke.require(not User.objects.filter(pk__in=ids).exists(), "CLEANUP_USERS_REMAIN")
            for model in (Asset, RecognitionJob, AssessmentJob):
                smoke.require(not model.objects.filter(owner_id__in=ids).exists(), "CLEANUP_OWNED_ROWS_REMAIN")
            smoke.require(not AuthSession.objects.filter(user_id__in=ids).exists(), "CLEANUP_SESSIONS_REMAIN")
            smoke.require(not any(storage.exists(name) for name, storage in saved_files.items()), "CLEANUP_FILES_REMAIN")
            report["cleanup"] = "verified" if report["threads_drained"] else "rows_removed_threads_not_drained"
        except Exception:
            report["cleanup"] = "failed"
            raise smoke.SmokeFailure("CLEANUP_FAILED") from None
        finally:
            errors = sum((item["errors"] for item in browsers), Counter())
            report["browse"] = {"accounts": 5, "target_requests_per_account_per_second": 1,
                                "attempts": sum(item["attempts"] for item in browsers),
                                "succeeded": sum(item["succeeded"] for item in browsers),
                                "errors": dict(errors), "error_count": sum(errors.values()),
                                **percentiles([latency for item in browsers for latency in item["latencies"]])}
            report["ai"] = {**ai, "errors": dict(ai["errors"]), "error_count": sum(ai["errors"].values()),
                            "target_interval_seconds": 10, "serial": True}
            if not math.isfinite(memory["mem_available_min_kib"]):
                memory["mem_available_min_kib"] = None
            report["host_memory"] = memory
    smoke.require(report["threads_drained"], "THREAD_DRAIN_TIMEOUT")
    smoke.require(report["browse"]["attempts"] > 0 and report["browse"]["error_count"] == 0,
                  "BROWSE_SAMPLE_FAILED")
    smoke.require(ai["attempts"] > 0 and not ai["errors"], "AI_SAMPLE_FAILED")
    if args.duration >= 30:
        smoke.require({sample["kind"] for sample in ai["samples"] if sample["status"] == "passed"}
                      == {"flower", "river"}, "BOTH_AI_MODELS_MUST_BE_SAMPLED")
    smoke.require(memory["samples"] > 0 and memory["errors"] == 0, "MEMORY_SAMPLE_FAILED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:18080")
    parser.add_argument("--duration", type=int, default=60, help="Sampling seconds, 1–180 (default: 60)")
    parser.add_argument("--flower-image", required=True)
    parser.add_argument("--river-image", required=True)
    args = parser.parse_args()
    report = {"status": "failed", "transport": "trusted_server_loopback_http",
              "public_https_verified": False, "wechat_verified": False,
              "m4_05_30_minute_acceptance": False, "requested_duration_seconds": args.duration,
              "cleanup": "not_needed"}
    started = time.monotonic()
    args.hard_deadline = started + 240
    for name in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM):
        signal.signal(name, smoke.interrupted)
    # Reserve a final five seconds if setup itself stalls until the alarm. Normal
    # cleanup/draining gets <=55s, always capped by this absolute 240s deadline.
    signal.setitimer(signal.ITIMER_REAL, 235)
    try:
        run(args, report)
        report["status"] = "passed"
    except Exception as error:
        report["failure"] = safe_failure(error)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        report["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
