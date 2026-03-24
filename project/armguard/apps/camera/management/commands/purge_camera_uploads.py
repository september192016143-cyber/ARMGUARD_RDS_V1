"""
Management command: purge_camera_uploads

Retention policy for CameraUploadLog:
  - Image file on disk  → deleted after FILE_RETENTION_DAYS  (default: 5 days)
  - Database record     → deleted after RECORD_RETENTION_DAYS (default: 3 years)

Run daily via cron (installed by update-server.sh):
    python manage.py purge_camera_uploads

Dry-run (shows counts, makes no changes):
    python manage.py purge_camera_uploads --dry-run
"""

import os
import logging

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from armguard.apps.camera.models import CameraUploadLog

logger = logging.getLogger(__name__)

# ── Retention windows ─────────────────────────────────────────────────────────
FILE_RETENTION_DAYS    = 5          # physical image file lifetime
RECORD_RETENTION_DAYS  = 3 * 365    # DB row lifetime (≈ 3 years; ignores leap days)


class Command(BaseCommand):
    help = (
        'Purge camera upload images older than 5 days, '
        'and delete DB records older than 3 years.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would be done without making any changes.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        now     = timezone.now()

        file_cutoff   = now - timedelta(days=FILE_RETENTION_DAYS)
        record_cutoff = now - timedelta(days=RECORD_RETENTION_DAYS)

        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY RUN] No changes will be made.'))

        # ── Phase 1: delete image files older than 5 days ────────────────────
        stale_files = CameraUploadLog.objects.filter(
            uploaded_at__lt=file_cutoff,
            file_purged_at__isnull=True,        # file not yet purged
            file_path__gt='',                   # path is not blank
        )

        file_deleted = 0
        file_missing = 0
        file_errors  = 0

        for log in stale_files.iterator(chunk_size=200):
            abs_path = os.path.join(settings.MEDIA_ROOT, log.file_path)
            if not dry_run:
                if os.path.isfile(abs_path):
                    try:
                        os.remove(abs_path)
                        file_deleted += 1
                    except OSError as exc:
                        file_errors += 1
                        logger.error(
                            'purge_camera_uploads: could not delete %s: %s',
                            abs_path, exc,
                        )
                        continue  # leave record untouched so we retry next run
                else:
                    # File already gone (e.g. manually removed); still mark purged
                    file_missing += 1

                log.file_path      = ''
                log.file_purged_at = now
                log.save(update_fields=['file_path', 'file_purged_at'])
            else:
                exists = os.path.isfile(abs_path)
                self.stdout.write(
                    f'  [DRY RUN] Would purge file: {log.file_path}'
                    f'{" (already missing)" if not exists else ""}'
                )
                file_deleted += 1

        self._report('Phase 1 — image files purged', file_deleted, file_missing, file_errors, dry_run)

        # Try to clean up empty date subdirectories (best-effort, not critical)
        if not dry_run:
            _cleanup_empty_dirs(os.path.join(settings.MEDIA_ROOT, 'camera_uploads'))

        # ── Phase 2: delete DB records older than 3 years ────────────────────
        old_records = CameraUploadLog.objects.filter(uploaded_at__lt=record_cutoff)
        record_count = old_records.count()

        if not dry_run:
            old_records.delete()
            self.stdout.write(self.style.SUCCESS(
                f'Phase 2 — DB records deleted : {record_count}'
            ))
        else:
            self.stdout.write(
                f'  [DRY RUN] Would delete {record_count} DB record(s) older than 3 years.'
            )

        if not dry_run:
            self.stdout.write(self.style.SUCCESS('purge_camera_uploads finished.'))

    # ── helpers ───────────────────────────────────────────────────────────────

    def _report(self, label, deleted, missing, errors, dry_run):
        prefix = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(
                f'{prefix}{label}: deleted={deleted}, already_missing={missing}, errors={errors}'
            )
        )


def _cleanup_empty_dirs(base_dir):
    """Remove empty date subdirectories under camera_uploads/ (best-effort)."""
    if not os.path.isdir(base_dir):
        return
    for name in os.listdir(base_dir):
        sub = os.path.join(base_dir, name)
        if os.path.isdir(sub):
            try:
                os.rmdir(sub)   # only succeeds if the directory is empty
            except OSError:
                pass            # still has files — skip silently
