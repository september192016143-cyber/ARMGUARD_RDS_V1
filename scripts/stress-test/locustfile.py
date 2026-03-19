"""
ArmGuard RDS V1 — Locust Load Test: Authenticated User Simulation
=================================================================
Simulates realistic multi-user sessions against the authenticated Django
views: Dashboard, Transaction list, and Print/Reprint TR.

Usage:
    # Run via stress_test.sh (recommended) or directly:
    export AUTH_COOKIE_HEADER="sessionid=xxx; csrftoken=yyy"
    locust -f scripts/stress-test/locustfile.py \\
           --headless -u 50 --spawn-rate 5 --run-time 30s \\
           --host http://<server-ip> \\
           --csv results/locust_c50

Required env vars:
    AUTH_COOKIE_HEADER   Full cookie string from auth_session.sh
    CSRF_TOKEN           CSRF token from auth_session.sh

Optional env vars (for per-user login — skipped when AUTH_COOKIE_HEADER is set):
    STRESS_TEST_USER     Django username for test account
    STRESS_TEST_PASSWORD Django password for test account
    TOTP_SECRET          Base32 TOTP secret for the test account (required for MFA)

Notes:
    - wait_time=between(1, 3) models realistic user think time.
      50 concurrent users with 1–3s wait ≈ 17–50 RPS sustained load.
    - All requests are GET only — no write operations are performed.
    - Requires: locust, pyotp  (pip install locust pyotp)
"""

import os
import re

import pyotp
import requests as _requests
from locust import HttpUser, between, events, task
from locust.exception import StopUser


# ── Configuration ─────────────────────────────────────────────────────────────
_BASE_URL       = os.environ.get("STRESS_BASE_URL", "http://localhost")
_AUTH_COOKIE    = os.environ.get("AUTH_COOKIE_HEADER", "")   # sessionid=x; csrftoken=y
_CSRF_TOKEN     = os.environ.get("CSRF_TOKEN", "")
_USERNAME       = os.environ.get("STRESS_TEST_USER", "")
_PASSWORD       = os.environ.get("STRESS_TEST_PASSWORD", "")
_TOTP_SECRET    = os.environ.get("TOTP_SECRET", "")

_LOGIN_URL      = "/accounts/login/"
_OTP_VERIFY_URL = "/accounts/otp/verify/"


# ── Validate configuration at startup ─────────────────────────────────────────
@events.init.add_listener
def on_locust_init(environment, **kwargs):
    if not _AUTH_COOKIE and not _USERNAME:
        environment.runner.quit()
        raise SystemExit(
            "\n[locustfile] ERROR: No authentication configured.\n"
            "Either:\n"
            "  A) Set AUTH_COOKIE_HEADER (from auth_session.sh), or\n"
            "  B) Set STRESS_TEST_USER + STRESS_TEST_PASSWORD (+ TOTP_SECRET if MFA)"
        )


def _parse_cookies(cookie_header: str) -> dict:
    """Parse 'key=val; key2=val2' into a dict."""
    result = {}
    for part in cookie_header.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def _extract_csrf(html: str) -> str:
    """Extract csrfmiddlewaretoken from an HTML form."""
    match = re.search(r'csrfmiddlewaretoken["\s]+value="([^"]+)"', html)
    return match.group(1) if match else ""


class ArmGuardUser(HttpUser):
    """
    Simulates a single authenticated ArmGuard user.
    Each virtual user logs in once (on_start), then repeatedly hits the
    three main authenticated views with realistic think time between requests.
    """

    # Think time: 1–3 seconds between tasks to model real user pacing.
    wait_time = between(1, 3)

    # Session state (set in on_start)
    _session_cookie: str = ""
    _csrf_token: str = ""

    def on_start(self):
        """Authenticate before running tasks. Called once per virtual user."""

        if _AUTH_COOKIE:
            # Fast path: reuse the shared session from auth_session.sh.
            # All virtual users share the same cookie — this is intentional for
            # CPU/Django-view load testing. For session-isolation tests, use
            # per-user login below.
            self._session_cookie = _AUTH_COOKIE
            self._csrf_token = _CSRF_TOKEN
        else:
            # Slow path: each virtual user logs in independently.
            self._login_as_user()

        # Verify the session works before hammering authenticated endpoints
        with self.client.get(
            "/dashboard/",
            headers={"Cookie": self._session_cookie},
            catch_response=True,
            name="[setup] GET /dashboard/ (verify)",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(
                    f"Session invalid — /dashboard/ returned {resp.status_code}. "
                    "Check credentials and MFA setup."
                )
                raise StopUser()
            resp.success()

    def _login_as_user(self):
        """
        Perform a full login flow (username → password → optional TOTP).
        Stores resulting cookies in self._session_cookie / self._csrf_token.
        """
        if not _USERNAME or not _PASSWORD:
            raise StopUser()

        # ── Step 1: GET login page ─────────────────────────────────────────────
        resp = self.client.get(
            _LOGIN_URL,
            name="[setup] GET /accounts/login/",
        )
        csrf = _extract_csrf(resp.text)
        if not csrf:
            raise StopUser()

        session_cookies = dict(resp.cookies)

        # ── Step 2: POST credentials ───────────────────────────────────────────
        resp = self.client.post(
            _LOGIN_URL,
            data={
                "username": _USERNAME,
                "password": _PASSWORD,
                "csrfmiddlewaretoken": csrf,
            },
            headers={
                "Referer": f"{_BASE_URL}{_LOGIN_URL}",
                "Cookie": f"csrftoken={csrf}",
            },
            allow_redirects=True,
            name="[setup] POST /accounts/login/",
        )

        session_id = resp.cookies.get("sessionid", "")
        csrf = resp.cookies.get("csrftoken", csrf)

        # ── Step 3: Handle TOTP redirect if required ───────────────────────────
        if _OTP_VERIFY_URL in resp.url:
            if not _TOTP_SECRET:
                raise StopUser()

            totp_code = pyotp.TOTP(_TOTP_SECRET).now()
            csrf_new = _extract_csrf(resp.text) or csrf

            resp = self.client.post(
                _OTP_VERIFY_URL,
                data={
                    "token": totp_code,
                    "csrfmiddlewaretoken": csrf_new,
                    "next": "dashboard",
                },
                headers={
                    "Referer": f"{_BASE_URL}{_OTP_VERIFY_URL}",
                    "Cookie": f"sessionid={session_id}; csrftoken={csrf_new}",
                },
                allow_redirects=True,
                name="[setup] POST /accounts/otp/verify/",
            )
            session_id = resp.cookies.get("sessionid", session_id)
            csrf = resp.cookies.get("csrftoken", csrf_new)

        if not session_id:
            raise StopUser()

        self._session_cookie = f"sessionid={session_id}; csrftoken={csrf}"
        self._csrf_token = csrf

    # ── Task helpers ──────────────────────────────────────────────────────────

    def _get(self, path: str, name: str | None = None):
        """Authenticated GET helper used by all tasks."""
        label = name or f"GET {path}"
        with self.client.get(
            path,
            headers={"Cookie": self._session_cookie},
            catch_response=True,
            name=label,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code in (302, 301):
                # Unexpected redirect — MFA session may have expired
                resp.failure(f"Redirect to {resp.headers.get('Location', '?')} — session expired?")
            elif resp.status_code in (502, 503):
                resp.failure(f"HTTP {resp.status_code} — Gunicorn/Nginx down?")
            else:
                resp.failure(f"HTTP {resp.status_code}")

    # ── Tasks (weighted) ──────────────────────────────────────────────────────

    @task(3)
    def dashboard(self):
        """Hit the main dashboard — heaviest Django view (inventory aggregates)."""
        self._get("/dashboard/", name="GET /dashboard/")

    @task(2)
    def transaction_list(self):
        """Transaction list view — paginated DB query."""
        self._get("/transactions/", name="GET /transactions/")

    @task(1)
    def reprint_tr(self):
        """Print/reprint TR page — tests the print app template rendering."""
        self._get("/print/reprint-tr/", name="GET /print/reprint-tr/")

    @task(1)
    def personnel_list(self):
        """Personnel list view."""
        self._get("/personnel/", name="GET /personnel/")

    @task(1)
    def inventory_list(self):
        """Inventory list view."""
        self._get("/inventory/", name="GET /inventory/")
