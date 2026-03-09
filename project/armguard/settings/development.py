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

# Use plain filesystem storage in development and during tests — CompressedManifest
# requires `collectstatic` to produce a manifest, which is not appropriate for
# local development or the test runner.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Show all SQL in the console during development (uncomment to enable):
# LOGGING['loggers']['django.db.backends'] = {
#     'handlers': ['console'],
#     'level': 'DEBUG',
#     'propagate': False,
# }
