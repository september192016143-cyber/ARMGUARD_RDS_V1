"""
G10 FIX: Management command — db_backup

Backs up the configured database:
- SQLite: hot-copy via sqlite3.Connection.backup() API (safe under concurrent use).
- PostgreSQL: pg_dump to a .sql.gz compressed dump.

A SHA-256 checksum sidecar (.sha256) is written alongside every backup file to
allow integrity verification.

Usage:
    python manage.py db_backup                          # saves to ./backups/
    python manage.py db_backup --output /var/backups/armguard
    python manage.py db_backup --keep 7                 # keep last 7 backups
"""
import os
import sqlite3
import hashlib
import shutil
import subprocess
import gzip
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
        db_conf = settings.DATABASES['default']
        engine = db_conf.get('ENGINE', '')
        stamp = timezone.localtime().strftime('%Y%m%d_%H%M%S')

        if 'postgresql' in engine or 'postgis' in engine:
            self._backup_postgres(db_conf, options, stamp)
        else:
            self._backup_sqlite(db_conf, options, stamp)

    # ------------------------------------------------------------------
    # PostgreSQL backup via pg_dump
    # ------------------------------------------------------------------
    def _backup_postgres(self, db_conf, options, stamp):
        db_name = db_conf.get('NAME', 'armguard')
        db_user = db_conf.get('USER', 'armguard')
        db_host = db_conf.get('HOST', '127.0.0.1')
        db_port = str(db_conf.get('PORT', '5432'))
        db_pass = db_conf.get('PASSWORD', '')

        if options['output']:
            out_dir = Path(options['output'])
        else:
            out_dir = Path(settings.BASE_DIR).parent / 'backups'
        out_dir.mkdir(parents=True, exist_ok=True)

        dest = out_dir / f'armguard_backup_{stamp}.sql.gz'

        env = os.environ.copy()
        if db_pass:
            env['PGPASSWORD'] = db_pass

        pg_dump_cmd = [
            'pg_dump',
            '-h', db_host,
            '-p', db_port,
            '-U', db_user,
            '-F', 'p',   # plain SQL
            '--no-password',
            db_name,
        ]

        try:
            result = subprocess.run(
                pg_dump_cmd,
                env=env,
                capture_output=True,
                check=True,
            )
            with gzip.open(dest, 'wb') as gz:
                gz.write(result.stdout)
        except subprocess.CalledProcessError as exc:
            err_msg = exc.stderr.decode(errors='replace')
            log_system_event(
                'BACKUP', 'backup_failed',
                message=f'pg_dump failed: {err_msg}',
                level='ERROR',
            )
            raise RuntimeError(f'pg_dump failed: {err_msg}') from exc

        size_kb = dest.stat().st_size // 1024
        self.stdout.write(self.style.SUCCESS(
            f'Backup saved: {dest}  ({size_kb} KB)'
        ))

        sha256 = hashlib.sha256(dest.read_bytes()).hexdigest()
        checksum_file = dest.with_suffix('.gz.sha256')
        checksum_file.write_text(f"{sha256}  {dest.name}\n", encoding='utf-8')
        self.stdout.write(f'  SHA-256: {sha256}')

        log_system_event(
            'BACKUP', 'backup_created',
            message=f'PostgreSQL backup created: {dest.name} ({size_kb} KB)',
            file=dest.name, size_kb=size_kb, sha256=sha256,
        )

        keep = max(1, options['keep'])
        backups = sorted(out_dir.glob('armguard_backup_*.sql.gz'))
        to_remove = backups[:-keep] if len(backups) > keep else []
        for old in to_remove:
            old.unlink(missing_ok=True)
            sidecar = old.with_suffix('.gz.sha256')
            if sidecar.exists():
                sidecar.unlink()
            self.stdout.write(f'  Removed old backup: {old.name}')

        if to_remove:
            log_system_event(
                'BACKUP', 'backup_rotated',
                message=f'Removed {len(to_remove)} old backup(s), kept last {keep}.',
                removed=len(to_remove), kept=keep,
            )

    # ------------------------------------------------------------------
    # SQLite backup via sqlite3.Connection.backup()
    # ------------------------------------------------------------------
    def _backup_sqlite(self, db_conf, options, stamp):
        db_path = Path(db_conf['NAME'])
        if not db_path.exists():
            self.stderr.write(self.style.ERROR(
                f'Database file not found: {db_path}'
            ))
            return

        out_dir = Path(options['output']) if options['output'] else db_path.parent / 'backups'
        out_dir.mkdir(parents=True, exist_ok=True)

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

        sha256 = hashlib.sha256(dest.read_bytes()).hexdigest()
        checksum_file = dest.with_suffix('.sha256')
        checksum_file.write_text(f"{sha256}  {dest.name}\n", encoding='utf-8')
        self.stdout.write(f'  SHA-256: {sha256}')

        log_system_event(
            'BACKUP', 'backup_created',
            message=f'Database backup created: {dest.name} ({size_kb} KB)',
            file=dest.name, size_kb=size_kb, sha256=sha256,
        )

        keep = max(1, options['keep'])
        backups = sorted(out_dir.glob('armguard_backup_*.sqlite3'))
        to_remove = backups[:-keep] if len(backups) > keep else []
        for old in to_remove:
            _secure_delete(old)
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
