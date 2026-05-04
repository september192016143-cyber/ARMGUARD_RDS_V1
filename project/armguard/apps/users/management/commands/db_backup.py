"""
G10 FIX: Management command — db_backup

Creates a hot-copy SQLite backup using the built-in sqlite3.connect().backup() API.
Safe to run while Django is serving live traffic — SQLite's WAL mode keeps reads
consistent during the backup.  A SHA-256 checksum sidecar (.sha256) is written
alongside every backup file to allow integrity verification.

Usage:
    python manage.py db_backup                          # saves to ./backups/
    python manage.py db_backup --output /var/backups/armguard
    python manage.py db_backup --keep 7                 # keep last 7 backups
"""
import os
import sqlite3
import hashlib
import shutil
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from armguard.apps.users.models import log_system_event


def _secure_delete(path: Path) -> None:
    """
    Overwrite a file with zeros before unlinking it.

    This defeats simple forensic recovery from the storage medium — a deleted
    SQLite backup should not be recoverable by listing freed disk blocks.
    On Linux/NVME the OS may still cache data in the journal, but this is a
    best-effort measure that is far better than a plain unlink().
    """
    try:
        size = path.stat().st_size
        with path.open('r+b') as fh:
            fh.write(b'\x00' * size)
            fh.flush()
            os.fsync(fh.fileno())
    except OSError:
        pass  # If overwrite fails, still delete the file.
    path.unlink(missing_ok=True)


class Command(BaseCommand):
    help = 'Create a hot-copy SQLite backup of the ArmGuard database.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output', type=str, default=None,
            help='Directory to write backup files (default: <project>/backups/).',
        )
        parser.add_argument(
            '--keep', type=int, default=10,
            help='Number of most-recent backup files to retain (default: 10).',
        )

    def handle(self, *args, **options):
        db_path = Path(settings.DATABASES['default']['NAME'])
        if not db_path.exists():
            self.stderr.write(self.style.ERROR(
                f'Database file not found: {db_path}'
            ))
            return

        out_dir = Path(options['output']) if options['output'] else db_path.parent / 'backups'
        out_dir.mkdir(parents=True, exist_ok=True)

        stamp = timezone.localtime().strftime('%Y%m%d_%H%M%S')
        dest = out_dir / f'armguard_backup_{stamp}.sqlite3'

        # Hot-copy via the sqlite3 backup API — safe under concurrent use.
        src_conn = sqlite3.connect(str(db_path))
        dst_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dst_conn, pages=50)
        except Exception as exc:
            log_system_event(
                'BACKUP', 'backup_failed',
                message=f'Database backup failed: {exc}',
                level='ERROR',
                dest=str(dest), error=str(exc),
            )
            raise
        finally:
            dst_conn.close()
            src_conn.close()

        size_kb = dest.stat().st_size // 1024
        self.stdout.write(self.style.SUCCESS(
            f'Backup saved: {dest}  ({size_kb} KB)'
        ))

        # Write SHA-256 checksum sidecar for offline integrity verification.
        sha256 = hashlib.sha256(dest.read_bytes()).hexdigest()
        checksum_file = dest.with_suffix('.sha256')
        checksum_file.write_text(f"{sha256}  {dest.name}\n", encoding='utf-8')
        self.stdout.write(f'  SHA-256: {sha256}')

        log_system_event(
            'BACKUP', 'backup_created',
            message=f'Database backup created: {dest.name} ({size_kb} KB)',
            file=dest.name, size_kb=size_kb, sha256=sha256,
        )

        # Prune old backups, keeping the N most recent.
        keep = max(1, options['keep'])
        backups = sorted(out_dir.glob('armguard_backup_*.sqlite3'))
        to_remove = backups[:-keep] if len(backups) > keep else []
        for old in to_remove:
            _secure_delete(old)  # Overwrite-then-delete for forensic safety.
            sidecar = old.with_suffix('.sha256')
            if sidecar.exists():
                sidecar.unlink()
            self.stdout.write(f'  Securely removed old backup: {old.name}')

        if to_remove:
            log_system_event(
                'BACKUP', 'backup_rotated',
                message=f'Removed {len(to_remove)} old backup(s), kept last {keep}.',
                removed=len(to_remove), kept=keep,
            )
