#!/usr/bin/env python3
"""Bounded HTTP smoke check; run as hyhq with the production environment loaded.

Example (environment loading and service-account switching belong to the operator):
  /opt/hyhq/venv/bin/python /opt/hyhq/current/scripts/production-smoke.py \
    --base-url https://greatdata.asia --flower-image /tmp/smoke-flower.jpg \
    --river-image /tmp/smoke-river.jpg --check-low-quality

Creates exactly two passwordless, temporary users through Django, then exercises
the public HTTPS API with internal API sessions. Never prints tokens, environment
values, image bytes, usernames, IDs, request URLs, or server response bodies.
Fixtures must be nonpersonal images known to produce flower recognition and at
least one class-9 river detection. This is a protocol check, not an accuracy test.
An explicit --trusted-loopback --base-url http://127.0.0.1:18080 checks only the
server-internal staging listener; it is not public HTTPS or WeChat acceptance.
"""

import argparse
import base64
import json
import logging
import math
import os
from pathlib import Path
import pwd
import signal
import sys
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


MAX_UPLOAD = 5 * 1024 * 1024
MAX_RESPONSE = 8 * 1024 * 1024
REQUEST_SECONDS = 8
POLL_SECONDS = 40
PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class SmokeFailure(Exception):
    """Messages are fixed check labels, safe for the report."""


def require(condition, label):
    if not condition:
        raise SmokeFailure(label)


def origin_from_url(value, trusted_loopback=False):
    parsed = urlsplit(value)
    if trusted_loopback:
        require(parsed.scheme == "http" and parsed.netloc == "127.0.0.1:18080"
                and parsed.path in {"", "/", "/api/v1", "/api/v1/"}
                and not parsed.query and not parsed.fragment,
                "TRUSTED_LOOPBACK_REQUIRES_HTTP_127_0_0_1_18080")
        return "http://127.0.0.1:18080"
    require(
        parsed.scheme == "https"
        and parsed.hostname == "greatdata.asia"
        and parsed.netloc == "greatdata.asia"
        and parsed.path in {"", "/", "/api/v1", "/api/v1/"}
        and not parsed.query
        and not parsed.fragment,
        "BASE_URL_MUST_BE_HTTPS_GREATDATA_ASIA",
    )
    return "https://greatdata.asia"


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Authorization must never follow a redirect, even to a related hostname.
        return None


class API:
    def __init__(self, origin, trusted_loopback=False):
        self.origin = origin
        self.trusted_loopback = trusted_loopback
        # Connect directly to the selected origin, with normal TLS verification.
        self.opener = build_opener(ProxyHandler({}), NoRedirects())
        self.requests = 0
        self.timings = []

    def request(self, method, path, token=None, body=None, content_type=None,
                expected=(200,), timeout=REQUEST_SECONDS):
        require(path.startswith("/api/v1/") and not path.startswith("//"), "INVALID_API_PATH")
        require(timeout > 0, "POLL_DEADLINE_EXCEEDED")
        headers = {"Accept": "application/json", "User-Agent": "HYHQ-production-smoke/1"}
        if self.trusted_loopback:
            headers.update({"Host": "greatdata.asia", "X-Forwarded-Proto": "https"})
        if token:
            headers["Authorization"] = "Bearer " + token
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(self.origin + path, data=body, headers=headers, method=method)
        started = time.monotonic()
        try:
            try:
                response = self.opener.open(request, timeout=min(timeout, REQUEST_SECONDS))
            except HTTPError as error:
                response = error
            with response:
                status = response.code
                response_headers = response.headers
                payload = response.read(MAX_RESPONSE + 1)
        except (URLError, TimeoutError, OSError):
            raise SmokeFailure("HTTP_REQUEST_FAILED") from None
        finally:
            self.requests += 1
            self.timings.append(round((time.monotonic() - started) * 1000))
        require(len(payload) <= MAX_RESPONSE, "HTTP_RESPONSE_TOO_LARGE")
        require(status in expected, "UNEXPECTED_HTTP_STATUS_" + str(status))
        return status, response_headers, payload

    def json(self, method, path, token=None, data=None, expected=(200,), timeout=REQUEST_SECONDS):
        body = json.dumps(data).encode() if data is not None else None
        status, headers, payload = self.request(
            method, "/api/v1/" + path, token, body,
            "application/json" if body is not None else None, expected, timeout,
        )
        if status == 204:
            require(not payload, "NONEMPTY_204_RESPONSE")
            return None
        require(headers.get_content_type() == "application/json", "EXPECTED_JSON_RESPONSE")
        try:
            document = json.loads(payload)
        except (ValueError, UnicodeError):
            raise SmokeFailure("INVALID_JSON_RESPONSE") from None
        require(isinstance(document, dict), "INVALID_JSON_ENVELOPE")
        if status >= 400:
            return document
        require("data" in document, "MISSING_DATA_ENVELOPE")
        return document["data"]

    def upload(self, token, image):
        boundary = "hyhq-smoke-" + uuid.uuid4().hex
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nrecognition\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"smoke.png\"\r\n"
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + image + f"\r\n--{boundary}--\r\n".encode()
        _, headers, payload = self.request(
            "POST", "/api/v1/uploads/", token, body,
            "multipart/form-data; boundary=" + boundary, (201,),
        )
        require(headers.get_content_type() == "application/json", "EXPECTED_UPLOAD_JSON")
        try:
            asset = json.loads(payload)["data"]
            asset_id = str(uuid.UUID(asset["id"]))
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise SmokeFailure("INVALID_UPLOAD_RESPONSE") from None
        require(asset.get("purpose") == "recognition", "INCORRECT_UPLOAD_PURPOSE")
        expected = "https://greatdata.asia" + f"/api/v1/uploads/{asset_id}/content/?variant=thumbnail"
        require(asset.get("thumbnail_url") == expected, "UNEXPECTED_PRIVATE_IMAGE_ORIGIN")
        return asset

    def image(self, asset, token, expected=(200,), variant="thumbnail"):
        asset_id = str(uuid.UUID(asset["id"]))
        status, headers, payload = self.request(
            "GET", f"/api/v1/uploads/{asset_id}/content/?variant={variant}", token, expected=expected,
        )
        if status == 200:
            require(headers.get_content_type() == "image/jpeg" and payload.startswith(b"\xff\xd8"),
                    "INVALID_PRIVATE_IMAGE")
            require("private" in headers.get("Cache-Control", "")
                    and "no-store" in headers.get("Cache-Control", ""), "PRIVATE_IMAGE_CACHE_POLICY")


def poll_jobs(api, token, jobs):
    deadline = time.monotonic() + POLL_SECONDS
    pending = dict(jobs)
    completed = {}
    while pending:
        for endpoint, job in list(pending.items()):
            if job.get("status") in {"queued", "running"}:
                remaining = deadline - time.monotonic()
                require(remaining > 0, "WORKER_POLL_EXCEEDED_40_SECONDS")
                job = api.json("GET", endpoint + job["id"] + "/", token, timeout=remaining)
                pending[endpoint] = job
            require(job.get("status") in {"queued", "running", "succeeded"}, "WORKER_JOB_FAILED")
            if job["status"] == "succeeded":
                completed[endpoint] = job
                del pending[endpoint]
        if pending:
            remaining = deadline - time.monotonic()
            require(remaining > 0, "WORKER_POLL_EXCEEDED_40_SECONDS")
            time.sleep(min(0.75, remaining))
    return completed


def check_recognition(job, low_quality=False):
    result = job.get("result", {})
    require(bool(result.get("model", {}).get("version")), "FLOWER_MODEL_VERSION_MISSING")
    if low_quality:
        require(result.get("decision") == "uncertain"
                and result.get("reason") == "LOW_IMAGE_QUALITY"
                and result.get("candidates") == [], "FLOWER_PIXEL_MUST_BE_UNCERTAIN")
        return
    require(result.get("decision") == "recognized", "FLOWER_MUST_BE_RECOGNIZED")
    candidates = result.get("candidates")
    require(isinstance(candidates, list) and bool(candidates), "FLOWER_CANDIDATES_MISSING")
    require(all(isinstance(item, dict) and finite_number(item.get("score"))
                and 0 <= item["score"] <= 1 for item in candidates), "INVALID_FLOWER_SCORES")


def check_assessment(job, low_quality=False):
    require(bool((job.get("model") or {}).get("version")), "RIVER_MODEL_VERSION_MISSING")
    require(bool(job.get("rule_version")), "RIVER_RULE_VERSION_MISSING")
    require(job.get("latitude") is None and job.get("longitude") is None, "UNEXPECTED_LOCATION")
    if low_quality:
        require(job.get("decision") == "uncertain" and job.get("reason") == "LOW_IMAGE_QUALITY"
                and job.get("detections") == [] and job.get("score") is None,
                "RIVER_PIXEL_MUST_BE_UNCERTAIN")
        return
    width, height = job.get("image_width"), job.get("image_height")
    require(finite_number(width) and width > 0 and finite_number(height) and height > 0,
            "RIVER_IMAGE_DIMENSIONS_MISSING")
    detections = job.get("detections")
    require(job.get("decision") == "assessed" and isinstance(detections, list) and bool(detections),
            "RIVER_CLASS_9_DETECTIONS_REQUIRED")
    for item in detections:
        require(isinstance(item, dict) and item.get("class_id") == 9
                and item.get("eval_category") == "floating_debris", "UNSUPPORTED_RIVER_DETECTION")
        score, box = item.get("confidence"), item.get("bbox")
        require(finite_number(score) and 0 <= score <= 1, "INVALID_RIVER_CONFIDENCE")
        require(isinstance(box, list) and len(box) == 4 and all(finite_number(x) for x in box),
                "INVALID_RIVER_BOUNDING_BOX")
        require(0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height,
                "RIVER_BOUNDING_BOX_OUTSIDE_IMAGE")


def run(args, report):
    origin = origin_from_url(args.base_url, args.trusted_loopback)
    report["transport"] = "trusted_server_loopback_http" if args.trusted_loopback else "public_https"
    report["public_https_verified"] = False
    images = []
    for filename in (args.flower_image, args.river_image):
        with Path(filename).open("rb") as source:
            image = source.read(MAX_UPLOAD + 1)
        require(0 < len(image) <= MAX_UPLOAD, "FIXTURE_SIZE_OUT_OF_RANGE")
        images.append(image)
    require(os.environ.get("ENV") == "production", "PRODUCTION_ENVIRONMENT_REQUIRED")
    require(pwd.getpwuid(os.geteuid()).pw_name == "hyhq", "RUN_AS_HYHQ_REQUIRED")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    django.setup()
    # This process only emits the aggregate report; server-side audit logging remains enabled.
    logging.disable(logging.CRITICAL)
    from django.conf import settings
    from accounts.models import AuthSession, User
    from accounts.services import issue_session
    from assets.models import Asset
    from assessments.models import AssessmentJob
    from recognition.models import RecognitionJob
    require(settings.ENV == "production" and not settings.DEBUG and not settings.ALLOW_DEV_AUTH,
            "PRODUCTION_SETTINGS_REQUIRED")

    api = API(origin, args.trusted_loopback)
    created_users = []
    saved_files = {}

    def remember_files():
        for asset in Asset.objects.filter(owner_id__in=[pk for pk, _ in created_users]):
            for field in (asset.original, asset.thumbnail):
                if field.name:
                    saved_files[field.name] = field.storage

    def assert_error(document, code):
        require(document.get("error", {}).get("code") == code, "EXPECTED_" + code)

    def scenario(owner, other, input_images, low_quality=False):
        report["stage"] = "low_quality_images" if low_quality else "real_images"
        assets = [api.upload(owner, content) for content in input_images]
        remember_files()
        require(assets[0]["id"] != assets[1]["id"], "JOBS_REQUIRE_SEPARATE_ASSETS")
        jobs = {}
        for endpoint, asset in zip(("recognition-jobs/", "assessment-jobs/"), assets):
            job = api.json("POST", endpoint, owner, {"asset_id": asset["id"]}, (201,))
            require(job.get("asset_id") == asset["id"], "INCORRECT_JOB_ASSET")
            jobs[endpoint] = job
            api.json("GET", endpoint + job["id"] + "/", other, expected=(403, 404))
            api.image(asset, owner)
            api.image(asset, owner, variant="original")
            api.image(asset, other, expected=(403, 404))
            api.image(asset, None, expected=(401,))
        for endpoint, asset in zip(("assessment-jobs/", "recognition-jobs/"), assets):
            rejected = api.json("POST", endpoint, owner, {"asset_id": asset["id"]}, (409,))
            assert_error(rejected, "ASSET_IN_USE")
        finals = poll_jobs(api, owner, jobs)
        check_recognition(finals["recognition-jobs/"], low_quality)
        check_assessment(finals["assessment-jobs/"], low_quality)
        report["worker_duration_ms"].append({
            "scenario": "low_quality" if low_quality else "real_images",
            "flower": finals["recognition-jobs/"].get("duration_ms"),
            "river": finals["assessment-jobs/"].get("duration_ms"),
            "river_detection_count": len(finals["assessment-jobs/"]["detections"]),
        })
        for (endpoint, job), asset in zip(jobs.items(), assets):
            api.json("DELETE", endpoint + job["id"] + "/", owner, expected=(204,))
            api.json("GET", endpoint + job["id"] + "/", owner, expected=(404,))
            api.image(asset, owner, expected=(404,))
            api.image(asset, owner, expected=(404,), variant="original")
        require(not Asset.objects.filter(owner_id=created_users[0][0]).exists(), "ASSETS_REMAIN_AFTER_JOB_DELETE")
        require(not any(storage.exists(name) for name, storage in saved_files.items()), "FILES_REMAIN_AFTER_JOB_DELETE")

    try:
        report["stage"] = "production_health"
        health = api.json("GET", "health/")
        require(health.get("status") == "ok" and health.get("dev_auth_enabled") is False,
                "PUBLIC_PRODUCTION_HEALTH_FAILED")
        require(health.get("features", {}).get("recognition") is True
                and health.get("features", {}).get("assessment") is True, "BOTH_MODELS_MUST_BE_ENABLED")
        report["public_https_verified"] = not args.trusted_loopback
        disabled = api.json("POST", "auth/dev/", data={"device_id": "production-smoke-disabled"}, expected=(404,))
        assert_error(disabled, "DEV_AUTH_DISABLED")
        report["checks"].append("production_health_and_dev_login_disabled")
        report["stage"] = "temporary_accounts"
        tokens = []
        for _ in range(2):
            username = "prod-smoke-" + uuid.uuid4().hex
            user_id = uuid.uuid4()
            created_users.append((user_id, username))
            user = User.objects.create_user(id=user_id, username=username, password=None)
            token, _ = issue_session(user)
            tokens.append(token)
            profile = api.json("GET", "me/", token)
            require(profile.get("id") == str(user.pk), "LOCAL_DB_AND_HTTPS_ACCOUNT_MISMATCH")
        owner, other = tokens
        scenario(owner, other, images)
        report["checks"].extend([
            "real_flower_recognized_and_river_class_9_detected",
            "private_images_owner_only_and_cross_account_job_isolation",
            "shared_asset_conflict_409_both_directions",
            "job_delete_removes_records_and_both_image_variants",
        ])
        if args.check_low_quality:
            scenario(owner, other, [PIXEL, PIXEL], low_quality=True)
            report["checks"].append("one_pixel_rejected_as_uncertain_by_both_workers")
        report["stage"] = "session_and_account_deletion"
        api.json("POST", "auth/logout/", other, expected=(204,))
        api.json("GET", "me/", other, expected=(401,))
        second_user = User.objects.get(pk=created_users[1][0])
        other, _ = issue_session(second_user)
        for token in (owner, other):
            api.json("DELETE", "me/", token, expected=(204,))
            api.json("GET", "me/", token, expected=(401,))
        report["checks"].append("logout_and_account_delete_revoke_sessions")
    finally:
        # Record only assets owned by this invocation, even if an upload response was lost.
        signal.setitimer(signal.ITIMER_REAL, 30)
        try:
            remember_files()
            for pk, username in created_users:
                User.objects.filter(pk=pk, username=username).delete()
            # File signals normally delete these. Retry only individually recorded names.
            for name, storage in saved_files.items():
                if storage.exists(name):
                    storage.delete(name)
            ids = [pk for pk, _ in created_users]
            require(not User.objects.filter(pk__in=ids).exists(), "CLEANUP_USERS_REMAIN")
            for model in (Asset, RecognitionJob, AssessmentJob):
                require(not model.objects.filter(owner_id__in=ids).exists(), "CLEANUP_OWNED_ROWS_REMAIN")
            require(not AuthSession.objects.filter(user_id__in=ids).exists(), "CLEANUP_SESSIONS_REMAIN")
            require(not any(storage.exists(name) for name, storage in saved_files.items()), "CLEANUP_FILES_REMAIN")
            report["cleanup"] = "verified"
        except Exception:
            report["cleanup"] = "failed"
            raise SmokeFailure("CLEANUP_FAILED") from None
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            report["http_requests"] = api.requests
            report["http_total_ms"] = sum(api.timings)
            report["http_max_ms"] = max(api.timings, default=0)


def interrupted(signum, frame):
    raise SmokeFailure("INTERRUPTED_OR_TOTAL_TIME_LIMIT")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True, help="HTTPS greatdata.asia origin (optional /api/v1 suffix)")
    parser.add_argument("--trusted-loopback", action="store_true",
                        help="Only use http://127.0.0.1:18080 with trusted proxy headers; no public TLS claim")
    parser.add_argument("--flower-image", required=True, help="Nonpersonal local flower fixture")
    parser.add_argument("--river-image", required=True, help="Nonpersonal local river fixture with class-9 detection")
    parser.add_argument("--check-low-quality", action="store_true", help="Also upload separate one-pixel fixtures")
    args = parser.parse_args()
    report = {"status": "failed", "checks": [], "worker_duration_ms": [], "cleanup": "not_needed"}
    started = time.monotonic()
    for name in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM):
        signal.signal(name, interrupted)
    signal.setitimer(signal.ITIMER_REAL, 180)
    try:
        run(args, report)
        report["status"] = "passed"
        report["stage"] = "completed"
    except SmokeFailure as error:
        report["failure"] = str(error)
    except Exception:
        # Do not expose exception strings: database/network errors can contain credentials.
        report["failure"] = "UNEXPECTED_LOCAL_ERROR"
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        report["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
