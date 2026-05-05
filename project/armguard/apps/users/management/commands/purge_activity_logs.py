"""
Management command: purge_activity_logs

Retention policy for ActivityLog:
  - DB record → deleted after RECORD_RETENTION_DAYS (default: 365 days / 1 year)

Run daily via cron (installed by update-server.sh):
    python manage.py purge_activity_logs

Dry-run (shows counts, makes no changes):
    python manage.py purge_activity_logs --dry-run
"""

import logging

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Retention window ──────────────────────────────────────────────────────────
RECORD_RETENTION_DAYS = 365  # 1 year


class Command(BaseCommand):
    help = 'Delete ActivityLog records older than 1 year to prevent unbounded DB growth.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would be deleted without making any changes.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        cutoff  = timezone.now() - timedelta(days=RECORD_RETENTION_DAYS)

        from armguard.apps.users.models import ActivityLog

        qs = ActivityLog.objects.filter(timestamp__lt=cutoff)
        count = qs.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'[DRY RUN] Would delete {count} ActivityLog record(s) '
                    f'older than {RECORD_RETENTION_DAYS} days (before {cutoff:%Y-%m-%d}).'
                )
            )
            return

        deleted, _ = qs.delete()
        msg = (
            f'purge_activity_logs finished. '
            f'Deleted {deleted} ActivityLog record(s) older than '
            f'{RECORD_RETENTION_DAYS} days (before {cutoff:%Y-%m-%d}).'
        )
        self.stdout.write(self.style.SUCCESS(msg))
        logger.info(msg)
