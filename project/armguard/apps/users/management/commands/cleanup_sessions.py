"""
G10 FIX: Management command — cleanup_sessions

Removes expired Django sessions from the database.

Usage:
    python manage.py cleanup_sessions           # dry-run (shows count only)
    python manage.py cleanup_sessions --delete  # actually delete expired rows
"""
from django.core.management.base import BaseCommand
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.utils import timezone
from armguard.apps.users.models import log_system_event


class Command(BaseCommand):
    help = 'Remove expired sessions from the database.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete',
            action='store_true',
            help='Actually delete expired sessions (default is dry-run).',
        )

    def handle(self, *args, **options):
        expired = Session.objects.filter(expire_date__lt=timezone.now())
        count = expired.count()

        if options['delete']:
            expired.delete()
            self.stdout.write(self.style.SUCCESS(
                f'Deleted {count} expired session(s).'
            ))
            log_system_event(
                'SESSION', 'sessions_cleaned',
                message=f'Deleted {count} expired session(s).',
                deleted=count,
            )
        else:
            self.stdout.write(
                f'Found {count} expired session(s). '
                f'Run with --delete to remove them.'
            )
