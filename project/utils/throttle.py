"""
M10 FIX: Simple cache-backed rate-limiter decorator.

Usage:
    @ratelimit(rate='60/m')
    def my_view(request): ...

Supports per-authenticated-user keying (preferred) and per-IP fallback for
anonymous requests.  Only the Django default cache backend is required —
no third-party packages needed.

Rate format:  "<count>/<period>"  where period is s / m / h / d.
"""
import functools

from django.core.cache import cache
from django.http import JsonResponse


def _is_ajax(request) -> bool:
    """Return True for fetch/XHR requests that expect a JSON response."""
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('Accept', '')
    )


def _compute_capacity_rate(period: str = 'm') -> tuple:
    """
    Derive a per-user rate limit from the server's CPU and RAM specs,
    mirroring gunicorn-autoconf.sh exactly:

      workers_base = (logical_cpus × 2) + 1
      ram_cap      = floor((RAM_MB − 1024) / 100), clamped [1, 32]
      workers      = 3          if RAM < 4 GB
                   = ram_cap    if workers_base > ram_cap
                   = workers_base otherwise

    Per-user rate  = workers × 10 requests, clamped to [20, 120] per minute.
    Larger servers allow more submissions per user; small/constrained servers
    are protected from a single user monopolising workers.

    Returns (limit: int, period_seconds: int).
    """
    import os
    cpu_count = os.cpu_count() or 1
    workers_base = (cpu_count * 2) + 1

    # Read RAM from /proc/meminfo (stdlib, no psutil needed).
    # Falls back to 4 GB on non-Linux hosts (dev machines, Windows CI).
    ram_mb = 4096
    try:
        with open('/proc/meminfo') as _f:
            for _line in _f:
                if _line.startswith('MemTotal:'):
                    ram_mb = int(_line.split()[1]) // 1024
                    break
    except OSError:
        pass

    if ram_mb > 1024:
        ram_cap = max(1, min((ram_mb - 1024) // 100, 32))
    else:
        ram_cap = 1

    if ram_mb < 4 * 1024:          # < 4 GB  — mirrors gunicorn-autoconf.sh low-RAM path
        workers = 3
    elif workers_base > ram_cap:
        workers = ram_cap
    else:
        workers = workers_base

    limit = max(20, min(workers * 10, 120))
    period_seconds = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[period]
    return limit, period_seconds


def ratelimit(rate: str = '60/m', block: bool = True, methods: list = None):
    """
    Decorator that limits how many times a view can be called in a window.

    rate:    '<count>/<period>' string, or 'auto' to derive the limit from
             server CPU/RAM specs via _compute_capacity_rate() (mirrors the
             gunicorn-autoconf.sh worker formula).
    methods: optional list of HTTP methods to rate-limit (e.g. ['POST']).
             Requests with other methods are passed through without counting.
             Default (None) counts all methods.
    """
    if rate == 'auto':
        limit, period_seconds = _compute_capacity_rate()
    else:
        _rate_count, period_code = rate.split('/')
        limit = int(_rate_count)
        period_seconds = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[period_code]
    _methods = [m.upper() for m in methods] if methods else None

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Skip rate-limiting entirely for methods not in the allow-list.
            if _methods is not None and request.method.upper() not in _methods:
                return view_func(request, *args, **kwargs)

            # Use authenticated user id as the key so rate limit is per-user,
            # not per-IP (which can be shared by NAT).
            if request.user.is_authenticated:
                key = f'rl:{view_func.__name__}:u:{request.user.pk}'
            else:
                key = f'rl:{view_func.__name__}:ip:{_client_ip(request)}'

            # C1 FIX: Atomic rate limiter.
            # cache.add() is atomic (SET NX in Redis / add() in Memcached).
            # cache.incr() is also atomic.  Together there is no read-then-write
            # race window where parallel requests can bypass the limit.
            added = cache.add(key, 1, period_seconds)  # Sets to 1 only if absent
            if not added:
                try:
                    count = cache.incr(key)  # Atomic increment
                except ValueError:
                    # Rare: key expired between add() check and incr(); reset counter.
                    cache.set(key, 1, period_seconds)
                    count = 1
            else:
                count = 1

            if count > limit:
                if block:
                    # For AJAX/fetch requests return JSON so the caller can handle it.
                    if _is_ajax(request):
                        return JsonResponse(
                            {'error': 'Too many requests. Please wait a moment before retrying.'},
                            status=429,
                        )
                    # For HTML form POSTs: add a flash message and redirect to a
                    # safe URL.  NEVER redirect to request.path — that re-hits the
                    # same rate-limited view, creating an infinite redirect loop.
                    from django.contrib import messages as _messages
                    from django.shortcuts import redirect as _redirect
                    _messages.error(
                        request,
                        'You are submitting too quickly. Please wait a moment before trying again.',
                    )
                    # Redirect to the HTTP Referer (previous page) if available
                    # and safe; fall back to the dashboard.
                    _referer = request.META.get('HTTP_REFERER', '')
                    from django.utils.http import url_has_allowed_host_and_scheme
                    if _referer and url_has_allowed_host_and_scheme(
                        url=_referer,
                        allowed_hosts={request.get_host()},
                        require_https=request.is_secure(),
                    ):
                        return _redirect(_referer)
                    return _redirect('dashboard')
                # non-blocking: let through but count was already incremented
                return view_func(request, *args, **kwargs)

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


def _client_ip(request) -> str:
    """Return the client's real IP, respecting X-Forwarded-For if present.

    SECURITY: Use the LAST entry, not the first.  The first entry is
    client-controlled and trivially spoofed (attacker sends their own
    X-Forwarded-For header).  The last entry is set by the immediate
    upstream proxy (nginx) and cannot be forged by the client.
    """
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[-1].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')
