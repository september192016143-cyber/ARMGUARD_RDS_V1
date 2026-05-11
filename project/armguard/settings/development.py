"""
ARMGUARD RDS — Development settings.

Usage:
    DJANGO_SETTINGS_MODULE=armguard.settings.development python manage.py runserver

Defaults are intentionally permissive for local development;
never use this file in production.
"""
import os
from .base import *  # noqa: F401, F403

# C2 FIX: Default to True in development for a good developer experience.
DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'

# Default to localhost only; override with DJANGO_ALLOWED_HOSTS in .env if needed.
_allowed = os.environ.get('DJANGO_ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [h.strip() for h in _allowed.split(',') if h.strip()] or ['localhost', '127.0.0.1']

# Enable the REST API by default in development so tests and local exploration work.
# In production, ARMGUARD_API_ENABLED is read from .env (default: False).
ARMGUARD_API_ENABLED = os.environ.get('ARMGUARD_API_ENABLED', 'True') == 'True'

# Use plain filesystem storage in development and during tests — CompressedManifest
# requires `collectstatic` to produce a manifest, which is not appropriate for
# local development or the test runner.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# P3-Low: Redirect all test-generated media (QR images, ID cards, etc.) to a
# temporary directory so test artefacts never accumulate in the repo working tree.
import sys as _sys
if 'test' in _sys.argv:
    import atexit as _atexit, shutil as _shutil, tempfile as _tempfile
    _TEST_MEDIA_DIR = _tempfile.mkdtemp(prefix='armguard_test_media_')
    MEDIA_ROOT = _TEST_MEDIA_DIR
    _atexit.register(_shutil.rmtree, _TEST_MEDIA_DIR, ignore_errors=True)

# Show all SQL in the console during development (uncomment to enable):
# LOGGING['loggers']['django.db.backends'] = {
#     'handlers': ['console'],
#     'level': 'DEBUG',
#     'propagate': False,
# }
