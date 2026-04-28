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


def ratelimit(rate: str = '60/m', block: bool = True):
    """Decorator that limits how many times a view can be called in a window."""
    limit, period_code = rate.split('/')
    limit = int(limit)
    period_seconds = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[period_code]

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
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
                    return JsonResponse(
                        {'error': 'Rate limit exceeded. Please wait before retrying.'},
                        status=429,
                    )
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
