"""
Activity logging middleware for ARMGUARD RDS.

Records every HTTP request to the ActivityLog database table.  Each entry is
auto-classified with a severity flag so reviewers can filter instantly:

  FLAG_NORMAL     — ordinary successful request
  FLAG_SLOW       — response took > 2 s (performance problem)
  FLAG_WARNING    — HTTP 404 (broken link, dead bookmark, probing)
  FLAG_SUSPICIOUS — HTTP 401 / 403 (access-denied or auth bypass attempt)
  FLAG_ERROR      — HTTP 5xx OR an uncaught Python exception

Skipped paths (no DB write):
  /static/*               — Django/WhiteNoise static files
  /media/*                — uploaded media files
  /favicon.ico            — browser auto-request
  /health/                — load-balancer health check
  /robots.txt             — search-engine crawler
  /api/v1/last-modified/  — polled every 60 s by every client tab (pure noise)

Captured per request:
  user, session_key, method, path, query_string, view_name, referer,
  status_code, response_ms, ip_address, user_agent,
  flag, exception_type, exception_message, search_query
"""

import time
import logging
from urllib.parse import parse_qs

from django.urls import resolve, Resolver404

logger = logging.getLogger(__name__)

# ── Noise suppression ──────────────────────────────────────────────────────────
_SKIP_PREFIXES = (
    '/static/',
    '/media/',
    '/favicon.ico',
    '/api/v1/last-modified/',   # polled every ~60 s by every client tab
)
_SKIP_PATHS = {
    '/health/',
    '/robots.txt',
}

# Query-string parameter names that carry search keywords.
_SEARCH_PARAMS = ('q', 'search', 'query', 'keyword', 'term')


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_client_ip(request):
    """Real client IP, honouring X-Forwarded-For set by Nginx."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _resolve_view_name(request):
    """Resolved URL name, e.g. 'transactions:create'.  Empty string on 404."""
    try:
        match = resolve(request.path_info)
        parts = [match.namespace, match.url_name] if match.namespace else [match.url_name]
        return ':'.join(p for p in parts if p) or ''
    except Resolver404:
        return ''


def _extract_search_query(query_string):
    """Return the first recognised search parameter value, or ''."""
    if not query_string:
        return ''
    try:
        params = parse_qs(query_string, keep_blank_values=False)
        for key in _SEARCH_PARAMS:
            val = params.get(key)
            if val:
                return val[0][:500]
    except Exception:
        pass
    return ''


def _compute_flag(status_code, response_ms, has_exception):
    """
    Classify this request into one severity level.

    Priority (highest wins):
      ERROR      — uncaught exception OR status >= 500
      SUSPICIOUS — 401 / 403
      WARNING    — 404
      SLOW       — response > 2 000 ms
      NORMAL     — everything else
    """
    if has_exception or (status_code and status_code >= 500):
        return 'ERROR'
    if status_code in (401, 403):
        return 'SUSPICIOUS'
    if status_code == 404:
        return 'WARNING'
    if response_ms and response_ms >= 2000:
        return 'SLOW'
    return 'NORMAL'


# ── Middleware ─────────────────────────────────────────────────────────────────

class ActivityLogMiddleware:
    """Record every non-static HTTP request to ActivityLog."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info

        # Fast-path: skip noise without touching the database.
        if path in _SKIP_PATHS or any(path.startswith(p) for p in _SKIP_PREFIXES):
            return self.get_response(request)

        start       = time.monotonic()
        exc_type    = ''
        exc_msg     = ''

        try:
            response = self.get_response(request)
        except Exception as exc:
            # Uncaught exception — record it before Django's 500 handler runs.
            exc_type = type(exc).__name__
            exc_msg  = str(exc)[:2000]
            elapsed  = int((time.monotonic() - start) * 1000)
            self._safe_record(request, 500, elapsed, exc_type, exc_msg)
            raise   # let Django handle the 500 response normally

        elapsed_ms = int((time.monotonic() - start) * 1000)
        self._safe_record(request, response.status_code, elapsed_ms, exc_type, exc_msg)
        return response

    @staticmethod
    def _safe_record(request, status_code, elapsed_ms, exc_type='', exc_msg=''):
        """Write one ActivityLog row.  Swallows all errors so logging never breaks a request."""
        try:
            ActivityLogMiddleware._record(request, status_code, elapsed_ms, exc_type, exc_msg)
        except Exception:
            logger.exception("ActivityLogMiddleware: failed to write activity log")

    @staticmethod
    def _record(request, status_code, elapsed_ms, exc_type, exc_msg):
        from armguard.apps.users.models import ActivityLog  # lazy — avoids circular import

        user = request.user if request.user.is_authenticated else None
        session_key = ''
        try:
            session_key = request.session.session_key or ''
        except Exception:
            pass

        method = request.method or 'OTHER'
        if method not in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'}:
            method = 'OTHER'

        qs = request.META.get('QUERY_STRING', '')

        ActivityLog.objects.create(
            # ── Actor ────────────────────────────────────────────────────────
            user=user,
            session_key=session_key,
            ip_address=_get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:512],
            # ── Request ──────────────────────────────────────────────────────
            method=method,
            path=request.path_info[:2048],
            query_string=qs[:2000],
            view_name=_resolve_view_name(request),
            referer=request.META.get('HTTP_REFERER', '')[:2048],
            # ── Response ─────────────────────────────────────────────────────
            status_code=status_code,
            response_ms=elapsed_ms,
            # ── Classification ───────────────────────────────────────────────
            flag=_compute_flag(status_code, elapsed_ms, bool(exc_type)),
            exception_type=exc_type,
            exception_message=exc_msg,
            search_query=_extract_search_query(qs),
        )
