"""
ARMGUARD RDS — Base settings shared across all environments.

Environment-specific overrides live in development.py and production.py.
Never use this file as DJANGO_SETTINGS_MODULE directly.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# M1 FIX: BASE_DIR goes up 3 levels (settings/ → armguard/ → project/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# M8 FIX: Auto-load .env so developers don't need to set env vars manually.
# load_dotenv() is a no-op when no .env file is present (production OK).
load_dotenv(BASE_DIR.parent / '.env')

# G5 FIX: Configurable admin URL — default 'admin' changes nothing, but set
# DJANGO_ADMIN_URL in .env to an obscure value (e.g. 'hq-panel') in production.
ADMIN_URL = os.environ.get('DJANGO_ADMIN_URL', 'admin').strip('/')

# C1 FIX: No hardcoded fallback — raise loudly on missing secret key.
_secret = os.environ.get('DJANGO_SECRET_KEY')
if not _secret:
    raise ValueError(
        "DJANGO_SECRET_KEY environment variable is not set. "
        "Set it in your .env file or shell before starting the server."
    )
SECRET_KEY = _secret

# L4 FIX: Magazine per-withdrawal limits exposed as settings (env-configurable).
ARMGUARD_PISTOL_MAGAZINE_MAX_QTY = int(os.environ.get('ARMGUARD_PISTOL_MAGAZINE_MAX_QTY', '4'))
_rifle_mag_env = os.environ.get('ARMGUARD_RIFLE_MAGAZINE_MAX_QTY')
# Default 2 — standard 2-magazine field issue.  Override via env var if needed.
ARMGUARD_RIFLE_MAGAZINE_MAX_QTY = int(_rifle_mag_env) if _rifle_mag_env else 2

# Unit identification settings for the Daily Firearms Evaluation printed report.
ARMGUARD_ARMORER_NAME          = os.environ.get('ARMGUARD_ARMORER_NAME', '')
ARMGUARD_ARMORER_RANK          = os.environ.get('ARMGUARD_ARMORER_RANK', '')
ARMGUARD_COMMANDER_NAME        = os.environ.get('ARMGUARD_COMMANDER_NAME', '')
ARMGUARD_COMMANDER_RANK        = os.environ.get('ARMGUARD_COMMANDER_RANK', '2LT')
ARMGUARD_COMMANDER_BRANCH      = os.environ.get('ARMGUARD_COMMANDER_BRANCH', 'PAF')
ARMGUARD_COMMANDER_DESIGNATION = os.environ.get('ARMGUARD_COMMANDER_DESIGNATION', 'Squadron Commander')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    # Custom apps
    'armguard.apps.dashboard',
    'armguard.apps.inventory',
    'armguard.apps.personnel',
    'armguard.apps.transactions',
    'armguard.apps.users',
    'armguard.apps.print',
    'armguard.apps.camera',
    'armguard.apps.profile',
    # G12 FIX: Django REST Framework + read-only API app.
    'rest_framework',
    'rest_framework.authtoken',
    'armguard.apps.api',
    # T1 FIX: OpenAPI 3.0 schema generation via drf-spectacular.
    # Exposes /api/v1/schema/ with machine-readable API documentation.
    'drf_spectacular',
    # G15 FIX: django-otp TOTP multi-factor authentication.
    'django_otp',
    'django_otp.plugins.otp_totp',
    'django_otp.plugins.otp_static',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # L6 FIX: WhiteNoise directly after SecurityMiddleware for compressed static files.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # G15 FIX: OTPMiddleware must come directly after AuthenticationMiddleware.
    'django_otp.middleware.OTPMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    # G4 FIX: Enforce single active session per user — new login invalidates the old one.
    'armguard.middleware.session.SingleSessionMiddleware',
    # XFrameOptionsMiddleware removed — CSP frame-ancestors 'self' in SecurityHeadersMiddleware
    # already handles clickjacking. Duplicate X-Frame-Options headers caused PDF iframe failures.
    # G15 FIX: Enforce OTP step for every authenticated session.
    'armguard.middleware.mfa.OTPRequiredMiddleware',
    # Security: CSP + Referrer-Policy response headers on every response.
    'armguard.middleware.security.SecurityHeadersMiddleware',
    # Activity logging: record every non-static request to ActivityLog table.
    # Placed last so status_code reflects the fully-processed response.
    'armguard.middleware.activity.ActivityLogMiddleware',
]

ROOT_URLCONF = 'armguard.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'armguard' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'armguard.context_processors.nav_permissions',
                'armguard.context_processors.session_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'armguard.wsgi.application'

# ---------------------------------------------------------------------------
# Database — env-switchable: SQLite (default/dev) or PostgreSQL (production).
#
# To use PostgreSQL set in .env:
#   DB_ENGINE=django.db.backends.postgresql
#   DB_NAME=armguard
#   DB_USER=armguard
#   DB_PASSWORD=<strong-password>
#   DB_HOST=127.0.0.1
#   DB_PORT=5432
#
# SQLite remains the default so existing installs are unaffected.
# PostgreSQL enables real row-level select_for_update(), atomic cache.incr(),
# and eliminates the file-level write lock that serialises all Gunicorn workers.
# ---------------------------------------------------------------------------
_db_engine = os.environ.get('DB_ENGINE', '').strip()
if _db_engine and _db_engine != 'django.db.backends.sqlite3':
    DATABASES = {
        'default': {
            'ENGINE': _db_engine,
            'NAME': os.environ.get('DB_NAME', 'armguard'),
            'USER': os.environ.get('DB_USER', 'armguard'),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
            'PORT': os.environ.get('DB_PORT', '5432'),
            # Keep connections alive for 10 min — avoids the TCP handshake
            # overhead on every request with 9 Gunicorn workers.
            'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', '600')),
            'CONN_HEALTH_CHECKS': True,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            # Reuse the open file handle across requests within each Gunicorn worker
            # process instead of opening+closing on every request.  600 s = 10 min.
            'CONN_MAX_AGE': 600,
            # Validate the kept-alive handle before use (guards against file-level
            # lock issues after a long idle period).
            'CONN_HEALTH_CHECKS': True,
            'OPTIONS': {
                # Wait up to 5 s when a second Gunicorn worker holds a write lock
                # before raising OperationalError: database is locked.
                'timeout': 5,
            },
        }
    }

# ---------------------------------------------------------------------------
# Cache — env-switchable: FileBasedCache (default) or Redis (production).
#
# FileBasedCache: shared across workers via the filesystem. Atomic cache.add()
# and cache.incr() are NOT guaranteed — race conditions possible under load.
#
# Redis: fully atomic add/incr, cross-process, survives worker recycles.
# Required for the rate-limiter in throttle.py to be truly race-free.
#
# To use Redis set in .env:
#   CACHE_BACKEND=django.core.cache.backends.redis.RedisCache
#   CACHE_LOCATION=redis://127.0.0.1:6379/1
# ---------------------------------------------------------------------------
_cache_backend = os.environ.get(
    'CACHE_BACKEND',
    'django.core.cache.backends.filebased.FileBasedCache',
).strip()
_cache_location = os.environ.get(
    'CACHE_LOCATION',
    str(BASE_DIR.parent / 'cache'),
).strip()

CACHES = {
    'default': {
        'BACKEND': _cache_backend,
        'LOCATION': _cache_location,
        'TIMEOUT': 300,  # 5 minutes default; individual cache.set() calls override
        # MAX_ENTRIES is a FileBasedCache-only option.  Django's RedisCache
        # backend forwards all OPTIONS keys to the redis connection constructor,
        # so passing MAX_ENTRIES with a Redis backend raises TypeError.
        # Include it only when the FileBasedCache backend is active.
        **({'OPTIONS': {'MAX_ENTRIES': 1000}}
           if _cache_backend == 'django.core.cache.backends.filebased.FileBasedCache'
           else {}),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    # G16-EXT2: Dynamic minimum length — reads the admin-configured value from
    # SystemSettings at validation time instead of a hardcoded constant.
    {'NAME': 'armguard.apps.users.validators.DynamicMinLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
    # G16-EXT: Prevent reuse of recent passwords — reads history_count from
    # SystemSettings at validation time instead of the OPTIONS constant.
    {
        'NAME': 'armguard.apps.users.validators.PasswordHistoryValidator',
        'OPTIONS': {'history_count': 5},  # fallback if DB unavailable
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Manila'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'armguard' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# L6 FIX: WhiteNoise compressed+versioned static files.
# See armguard/storage.py for the custom backend that skips URL-rewriting on
# .mjs files (large PDF.js bundles that would be corrupted by the rewriter).
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "armguard.storage.ArmguardStaticStorage"},
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
CARD_TEMPLATES_DIR = BASE_DIR / 'card_templates'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# M7 FIX: Session expires after 8 hours (one duty shift).
SESSION_COOKIE_AGE = 28800
SESSION_COOKIE_HTTPONLY = True
# IMPORTANT: CSRF_COOKIE_HTTPONLY=True means JavaScript cannot read the CSRF
# cookie via document.cookie. To get the CSRF token in JS, use the {{ csrf_token }}
# template variable or the csrfmiddlewaretoken value from a {% csrf_token %} form field.
CSRF_COOKIE_HTTPONLY = True

# G12 FIX: DRF — session + token auth, read-only default permission, pagination,
# and API-level throttling to prevent bulk scraping.
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    # JSON-only renderer in all environments — the DRF browsable API form exposes
    # sensitive military PII (names, ranks, service IDs) as a web UI. Production
    # settings also enforce JSONRenderer only.
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    # API throttle — 30 requests/minute for authenticated users (override per-view
    # if a specific endpoint needs a different limit).
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '10/minute',   # anonymous — should never happen (IsAuthenticated default)
        'user': '30/minute',   # authenticated users
        # S01 FIX: strict throttle for token auth endpoint (5/min per IP)
        'token_auth': '5/minute',
        # PII endpoints (Personnel, Transaction viewsets): 60 req/hour per user
        # to prevent bulk scraping of military records.
        'pii': '60/hour',
    },
    # T1 FIX: Use drf-spectacular for OpenAPI schema generation.
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# L7 FIX: Security headers safe to set in all environments.
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'SAMEORIGIN'  # Allow self-framing for TR/PDF iframes; external clickjacking still blocked
SECURE_CONTENT_TYPE_NOSNIFF = True

# ---------------------------------------------------------------------------
# T1 FIX: OpenAPI schema settings (drf-spectacular)
# Schema is available at /api/v1/schema/ — staff login required.
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    'TITLE': 'ArmGuard RDS API',
    'DESCRIPTION': (
        'Read-only REST API for the ArmGuard Resource Data System. '
        'All write operations must go through the web UI to preserve '
        'business-rule enforcement (audit logs, select_for_update, etc.).'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,  # Don't include /api/v1/schema/ in itself
    'SERVE_PERMISSIONS': ['rest_framework.permissions.IsAdminUser'],
    'COMPONENT_SPLIT_REQUEST': True,
    'SORT_OPERATIONS': True,
}
SECURE_REFERRER_POLICY = 'same-origin'

# G15: TOTP issuer name shown in authenticator apps (e.g. Google Authenticator).
# Without this, only the username is displayed — no system label.
OTP_TOTP_ISSUER = 'ArmGuard RDS'

# G12: Opt-in API — set ARMGUARD_API_ENABLED=True in .env to expose /api/v1/.
# Defaults to False so fresh deployments do not expose the endpoint until needed.
ARMGUARD_API_ENABLED = os.environ.get('ARMGUARD_API_ENABLED', 'False') == 'True'

# ---------------------------------------------------------------------------
# Structured async logging.
#
# A single QueueListener background thread per Gunicorn worker drains the
# log queue and writes to the rotating file.  Every _logger.xxx() call on a
# request thread just enqueues a record and returns instantly — zero I/O on
# the request thread regardless of disk speed.
# ---------------------------------------------------------------------------
import logging as _logging
import logging.handlers as _log_handlers
import queue as _queue

LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# Build the real file + console handlers that the listener will use.
_log_formatter = _logging.Formatter('[%(levelname)s] %(asctime)s %(name)s %(process)d %(message)s')

_file_handler = _log_handlers.RotatingFileHandler(
    str(LOG_DIR / 'armguard.log'),
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5,
    encoding='utf-8',
)
_file_handler.setFormatter(_log_formatter)
_file_handler.setLevel(_logging.INFO)

_console_handler = _logging.StreamHandler()
_console_handler.setFormatter(_log_formatter)
_console_handler.setLevel(_logging.WARNING)

# Unbounded queue: enqueue never blocks a request thread.
_log_queue: _queue.Queue = _queue.Queue(-1)

# QueueListener runs one background thread per worker process.
# respect_handler_level=True: each downstream handler applies its own level.
_log_listener = _log_handlers.QueueListener(
    _log_queue, _file_handler, _console_handler, respect_handler_level=True
)
_log_listener.start()

# Django LOGGING dict — route every logger through QueueHandler.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'queue': {
            'class': 'logging.handlers.QueueHandler',
            'queue': _log_queue,
        },
    },
    'loggers': {
        'armguard': {
            'handlers': ['queue'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['queue'],
            'level': 'WARNING',
            'propagate': False,
        },
        # Capture 500 tracebacks and 4xx errors.
        'django.request': {
            'handlers': ['queue'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

# ---------------------------------------------------------------------------
# SQLite WAL mode
# Activate Write-Ahead Logging on every new connection so concurrent reads
# are not blocked by in-progress writes.  Without WAL (default rollback
# journal) any write serialises ALL access, including reads, which causes
# visible latency with 2+ Gunicorn workers.  WAL allows N readers + 1 writer
# simultaneously and pairs correctly with CONN_MAX_AGE above.
# PRAGMA synchronous=NORMAL is the recommended companion: it is crash-safe
# (data survives OS crash) while halving fsync calls vs the FULL default.
# ---------------------------------------------------------------------------
from django.db.backends.signals import connection_created as _db_conn_created  # noqa: E402


def _activate_sqlite_wal(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        connection.cursor().execute('PRAGMA journal_mode=WAL;')
        connection.cursor().execute('PRAGMA synchronous=NORMAL;')
        # 32 MB in-memory page cache per connection (negative = kibibytes).
        # Reduces disk I/O on repeated queries against the same pages.
        connection.cursor().execute('PRAGMA cache_size=-32768;')
        # Store temp tables / indices in RAM rather than a temp file.
        connection.cursor().execute('PRAGMA temp_store=MEMORY;')


_db_conn_created.connect(_activate_sqlite_wal)
