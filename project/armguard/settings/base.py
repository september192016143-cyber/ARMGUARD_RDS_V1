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
ARMGUARD_RIFLE_MAGAZINE_MAX_QTY = int(_rifle_mag_env) if _rifle_mag_env else None

# Unit identification settings for the Daily Firearms Evaluation printed report.
ARMGUARD_ARMORER_NAME          = os.environ.get('ARMGUARD_ARMORER_NAME', '')
ARMGUARD_ARMORER_RANK          = os.environ.get('ARMGUARD_ARMORER_RANK', '')
ARMGUARD_COMMANDER_NAME        = os.environ.get('ARMGUARD_COMMANDER_NAME', 'RIZALDY C HERMOSO II')
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
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # G15 FIX: Enforce OTP step for every authenticated session.
    'armguard.middleware.mfa.OTPRequiredMiddleware',
    # Security: CSP + Referrer-Policy response headers on every response.
    'armguard.middleware.security.SecurityHeadersMiddleware',
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
            ],
        },
    },
]

WSGI_APPLICATION = 'armguard.wsgi.application'

# ---------------------------------------------------------------------------
# Cache — LocMemCache (per-process, in-memory).
# Fast enough for LAN deployments; upgrade to FileBasedCache or Redis if
# multi-process cross-worker consistency ever becomes required.
# ---------------------------------------------------------------------------
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'armguard-default',
        'TIMEOUT': 300,  # 5 minutes default; individual cache.set() calls override as needed
    }
}

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

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 12},
    },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
    # G16-EXT: Prevent reuse of recent passwords (last 5).
    {
        'NAME': 'armguard.apps.users.validators.PasswordHistoryValidator',
        'OPTIONS': {'history_count': 5},
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
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
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

# M12 FIX: Structured logging to rotating file.
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'armguard.log',
            'maxBytes': 5 * 1024 * 1024,  # 5 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'armguard': {
            'handlers': ['file', 'console'],
            'level': 'WARNING',
            'propagate': False,
        },
        # N3 FIX: Transaction audit events at INFO level.
        'armguard.transactions': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': False,
        },
        # N6 FIX: Signal-based audit events for all inventory/personnel saves.
        'armguard.audit': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['file'],
            'level': 'WARNING',
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


_db_conn_created.connect(_activate_sqlite_wal)
