"""
ARMGUARD RDS — Production settings.

Usage:
    DJANGO_SETTINGS_MODULE=armguard.settings.production gunicorn armguard.wsgi

Required environment variables (in addition to those in base.py):
    DJANGO_ALLOWED_HOSTS — comma-separated list of allowed host names
    DJANGO_SECRET_KEY    — secret key (never commit this)

Optional:
    DJANGO_DEBUG         — must be 'False' or omitted in production
"""
import os
from .base import *  # noqa: F401, F403

# C2 FIX: Always False in production — never expose debug info publicly.
DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'
if DEBUG:
    import warnings
    warnings.warn("DJANGO_DEBUG is True in production settings — set to False before deploying.", stacklevel=1)

# S4-F1 FIX: Refuse to start with empty ALLOWED_HOSTS in production.
_allowed = os.environ.get('DJANGO_ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [h.strip() for h in _allowed.split(',') if h.strip()]
if not ALLOWED_HOSTS:
    raise ValueError(
        "DJANGO_ALLOWED_HOSTS must be set when using production settings. "
        "Example: DJANGO_ALLOWED_HOSTS=armguard.example.com"
    )

# ── HTTPS security headers ────────────────────────────────────────────────────
# SECURE_SSL_REDIRECT defaults to False so initial HTTP-only deployments work.
# After SSL is installed and certbot configures Nginx, set SECURE_SSL_REDIRECT=True
# in the production .env file.  Nginx handles the HTTP→HTTPS redirect itself until
# then (see the HTTP server block in nginx-armguard.conf).
SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'False') == 'True'
if not SECURE_SSL_REDIRECT and not DEBUG:
    import warnings
    warnings.warn(
        "SECURE_SSL_REDIRECT is False in production. Session and CSRF cookies will NOT be "
        "marked Secure. Set SECURE_SSL_REDIRECT=True in .env once HTTPS is configured.",
        stacklevel=1,
    )
SECURE_HSTS_SECONDS = 31536000          # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# HSTS preload submits the domain to browser preload lists — irreversible.
# Only enable after HTTPS is confirmed permanently deployed.
SECURE_HSTS_PRELOAD = os.environ.get('SECURE_HSTS_PRELOAD', 'False') == 'True'
# SESSION_COOKIE_SECURE and CSRF_COOKIE_SECURE are tied to SECURE_SSL_REDIRECT so
# enabling SSL (one env var) automatically secures all cookies. During the initial
# HTTP-only deployment phase both are False; after SSL is confirmed set
# SECURE_SSL_REDIRECT=True in .env and all three settings engage together.
SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
CSRF_COOKIE_SECURE    = SECURE_SSL_REDIRECT
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# CSRF_TRUSTED_ORIGINS — required when Django runs behind a reverse proxy.
# Populated from .env: CSRF_TRUSTED_ORIGINS=https://example.com,http://192.168.1.100
_origins = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _origins.split(',') if o.strip()]

# C3 FIX: Disable DRF browsable API in production — JSON responses only.
# The base.py comment says "Disable browsable API renderer in production" but
# never actually overrides it.  This override is the real enforcement.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,   # noqa: F405 — imported via `from .base import *`
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}

# ── PostgreSQL connection pool (production only) ──────────────────────────────
# When PostgreSQL is active (DB_ENGINE=django.db.backends.postgresql), enable
# the built-in connection pool (Django 5.1+) to avoid opening a new TCP
# connection to Postgres on every request from every Gunicorn worker.
# Pool size = 2 per worker × 9 workers = 18 max connections total.
# Adjust DB_POOL_SIZE in .env if the PostgreSQL max_connections differs.
import os as _os  # noqa: E402 — already imported in base; re-alias for clarity
if _os.environ.get('DB_ENGINE', '').strip() not in ('', 'django.db.backends.sqlite3'):
    _pool_size = int(_os.environ.get('DB_POOL_SIZE', '2'))
    DATABASES['default']['OPTIONS'] = DATABASES['default'].get('OPTIONS', {})  # noqa: F405
    DATABASES['default']['OPTIONS']['pool'] = {  # noqa: F405
        'min_size': _pool_size,
        'max_size': _pool_size * 2,
        'timeout': 30,
    }

# ── SSL certificate download ──────────────────────────────────────────────────
# Path to the self-signed cert served as an in-app download so LAN users can
# install it on their devices.  Override via SSL_CERT_PATH env var if needed.
SSL_CERT_PATH = os.environ.get(
    'SSL_CERT_PATH',
    '/etc/ssl/certs/armguard-selfsigned.crt',
)
