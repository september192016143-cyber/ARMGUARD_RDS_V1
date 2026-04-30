"""
Activity logging middleware for ARMGUARD RDS.

Records every HTTP request to the ActivityLog database table, giving admins
a full picture of who visited what, when, from where, and how fast it responded.

Skipped paths (no DB write):
  - Static file requests  (/static/*)
  - Media file requests   (/media/*)
  - Health check endpoint (/health/)
  - Favicon               (/favicon.ico)
  - Django admin assets   (/secure-admin-*/jsi18n/)

Captured per request:
  user, session_key, method, path, query_string, view_name, referer,
  status_code, response_ms, ip_address, user_agent, timestamp
"""

import time
import logging

from django.urls import resolve, Resolver404

logger = logging.getLogger(__name__)

# Prefixes that produce high-volume noise with no audit value.
_SKIP_PREFIXES = (
    '/static/',
    '/media/',
    '/favicon.ico',
)
_SKIP_PATHS = {
    '/health/',
    '/robots.txt',
}


def _get_client_ip(request):
    """Return the real client IP, respecting X-Forwarded-For from Nginx."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _resolve_view_name(request):
    """Return the URL name for the current path, e.g. 'transactions:create'."""
    try:
        match = resolve(request.path_info)
        parts = [match.namespace, match.url_name] if match.namespace else [match.url_name]
        return ':'.join(p for p in parts if p) or ''
    except Resolver404:
        return ''


class ActivityLogMiddleware:
    """Record every non-static HTTP request to ActivityLog."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info

        # Skip noise paths — do not touch the DB for these.
        if path in _SKIP_PATHS or any(path.startswith(p) for p in _SKIP_PREFIXES):
            return self.get_response(request)

        start = time.monotonic()
        response = self.get_response(request)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        try:
            self._record(request, response, elapsed_ms)
        except Exception:
            # Never let logging break a request.
            logger.exception("ActivityLogMiddleware: failed to write log")

        return response

    @staticmethod
    def _record(request, response, elapsed_ms):
        from armguard.apps.users.models import ActivityLog  # lazy import — avoids circular

        user = request.user if request.user.is_authenticated else None
        session_key = ''
        try:
            session_key = request.session.session_key or ''
        except Exception:
            pass

        method = request.method or 'OTHER'
        if method not in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'}:
            method = 'OTHER'

        ActivityLog.objects.create(
            user=user,
            session_key=session_key,
            method=method,
            path=request.path_info[:2048],
            query_string=request.META.get('QUERY_STRING', '')[:2000],
            view_name=_resolve_view_name(request),
            referer=request.META.get('HTTP_REFERER', '')[:2048],
            status_code=response.status_code,
            response_ms=elapsed_ms,
            ip_address=_get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:512],
        )
