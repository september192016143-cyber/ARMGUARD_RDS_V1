import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# M8 FIX: Auto-load .env so developers don't need to set env vars manually.
# load_dotenv() is a no-op when no .env file is present (production OK).
load_dotenv(BASE_DIR.parent / '.env')

# C1 FIX: No hardcoded fallback — raise loudly on missing secret key.
_secret = os.environ.get('DJANGO_SECRET_KEY')
if not _secret:
    raise ValueError(
        "DJANGO_SECRET_KEY environment variable is not set. "
        "Set it in your .env file or shell before starting the server."
    )
SECRET_KEY = _secret

# C2 FIX: Default to False — must opt in to debug mode explicitly.
DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'

_allowed = os.environ.get('DJANGO_ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [h for h in _allowed.split(',') if h] if _allowed else (['localhost', '127.0.0.1'] if DEBUG else [])

# S4-F1 FIX: Refuse to start in production with no allowed hosts — fail clearly
# rather than silently rejecting every request with a 400.
if not DEBUG and not ALLOWED_HOSTS:
    raise ValueError(
        "DJANGO_ALLOWED_HOSTS environment variable must be set when DEBUG=False. "
        "Example: DJANGO_ALLOWED_HOSTS=armguard.example.com,www.armguard.example.com"
    )

# L4 FIX: Magazine per-withdrawal limits are exposed as settings so they can be
# adjusted per deployment via environment variable rather than requiring a code change.
# Default values mirror the current spec: Pistol=4, Rifle=no hard cap.
ARMGUARD_PISTOL_MAGAZINE_MAX_QTY = int(os.environ.get('ARMGUARD_PISTOL_MAGAZINE_MAX_QTY', '4'))
_rifle_mag_env = os.environ.get('ARMGUARD_RIFLE_MAGAZINE_MAX_QTY')
ARMGUARD_RIFLE_MAGAZINE_MAX_QTY = int(_rifle_mag_env) if _rifle_mag_env else None

# Unit identification settings used on the Daily Firearms Evaluation printed report.
# Override via environment variables; leave blank to show a blank signature line.
ARMGUARD_ARMORER_NAME          = os.environ.get('ARMGUARD_ARMORER_NAME', '')
ARMGUARD_ARMORER_RANK          = os.environ.get('ARMGUARD_ARMORER_RANK', '')
ARMGUARD_ARMORER_BRANCH        = os.environ.get('ARMGUARD_ARMORER_BRANCH', 'PAF')
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
    'armguard.apps.camera',
    # G15: django-otp — TOTP models & OTPMiddleware (is_verified() on request.user)
    'django_otp',
    'django_otp.plugins.otp_totp',
    'django_otp.plugins.otp_static',
    # M4/M5 FIX: Removed empty skeleton apps (armguard.apps.registration,
    # armguard.apps.core, armguard.apps.utils) — no models, no migrations,
    # not referenced in URLs. Keeping them registered wastes app-registry
    # resolution time and confuses onboarding developers.
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # L6 FIX: WhiteNoise must be directly after SecurityMiddleware so it can
    # serve compressed/immutable static files with a long cache TTL.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # G15: django-otp sets request.user.is_verified() from session (must follow AuthenticationMiddleware).
    'django_otp.middleware.OTPMiddleware',
    # G15: ArmGuard custom enforcement — redirects unverified sessions to /accounts/otp/verify/.
    #      Controlled by SystemSettings.mfa_required (superuser can toggle via UI Settings page).
    'armguard.middleware.mfa.OTPRequiredMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    # XFrameOptionsMiddleware removed — CSP frame-ancestors 'self' in SecurityHeadersMiddleware
    # already handles clickjacking. Keeping the Django middleware caused duplicate/conflicting
    # X-Frame-Options headers (SAMEORIGIN vs DENY) that blocked PDF iframes in Chrome.
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
                'armguard.context_processors.session_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'armguard.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Manila'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'armguard' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# L6 FIX: WhiteNoise compressed+versioned static files.  Django 4.2+ uses
# the STORAGES dict instead of the deprecated STATICFILES_STORAGE setting.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
# Card and PDF template files (not served publicly — stored outside media/)
CARD_TEMPLATES_DIR = BASE_DIR / 'card_templates'

# ── Google Sheets import ──────────────────────────────────────────────────────
# Path to the service account JSON key file.
# Set GOOGLE_SA_JSON=/path/to/service-account.json in your .env file.
# If not set, the "Import from Google Sheet" feature will be disabled.
import os as _os
GOOGLE_SA_JSON = _os.environ.get('GOOGLE_SA_JSON', '')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# M7 FIX: Session expires after 8 hours (one duty shift). Default is 2 weeks.
SESSION_COOKIE_AGE = 28800  # 8 hours in seconds
SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript from reading session cookie
CSRF_COOKIE_HTTPONLY = True

# Client-side idle auto-logout: warn after 29 min, force logout at 30 min.
IDLE_SESSION_TIMEOUT = 1800  # seconds (30 minutes of inactivity)

# L7 FIX: Production HTTPS security headers.
# These are safe to set even in development (they only apply via HTTPS).
# In production, also set: SECURE_SSL_REDIRECT=True, SECURE_HSTS_SECONDS=31536000
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'SAMEORIGIN'  # Allow self-framing for TR/PDF iframes; external clickjacking blocked by CSP frame-ancestors
SECURE_CONTENT_TYPE_NOSNIFF = True

# M12 FIX: Structured logging to file.
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
        # N3 FIX: Audit-critical transaction events logged at INFO so every
        # Withdrawal and Return is recorded in armguard.log.
        'armguard.transactions': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': False,
        },
        # N6 FIX: Route signals.py audit events (post_save/post_delete for all
        # inventory and personnel models) to the log file at INFO level.
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

# Path to the self-signed SSL certificate served as a download to LAN clients.
# Override via SSL_CERT_PATH env var if the cert lives elsewhere.
SSL_CERT_PATH = os.environ.get(
    'SSL_CERT_PATH',
    '/etc/ssl/certs/armguard-selfsigned.crt',
)