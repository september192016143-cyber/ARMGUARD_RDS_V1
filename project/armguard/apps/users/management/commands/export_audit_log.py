"""
G10 FIX: Management command — export_audit_log

Exports AuditLog records to a CSV file.

Usage:
    python manage.py export_audit_log
    python manage.py export_audit_log --days 30
    python manage.py export_audit_log --action LOGIN
    python manage.py export_audit_log --user admin
    python manage.py export_audit_log --output /tmp/audit.csv
"""
import csv
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from armguard.apps.users.models import log_system_event


class Command(BaseCommand):
    help = 'Export AuditLog records to CSV.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=None,
            help='Export only records from the last N days.',
        )
        parser.add_argument(
            '--action', type=str, default=None,
            help='Filter by action type (e.g. LOGIN, LOGOUT, CREATE, UPDATE, DELETE).',
        )
        parser.add_argument(
            '--user', type=str, default=None,
            help='Filter by username.',
        )
        parser.add_argument(
            '--output', type=str, default='audit_log.csv',
            help='Output CSV file path (default: audit_log.csv).',
        )

    def handle(self, *args, **options):
        from armguard.apps.users.models import AuditLog

        qs = AuditLog.objects.select_related('user').order_by('-timestamp')

        if options['days']:
            since = timezone.now() - timedelta(days=options['days'])
            qs = qs.filter(timestamp__gte=since)

        if options['action']:
            qs = qs.filter(action=options['action'].upper())

        if options['user']:
            qs = qs.filter(user__username=options['user'])

        out_path = options['output']
        count = 0

        with open(out_path, 'w', newline='', encoding='utf-8') as fh:
            writer = csv.writer(fh)
            writer.writerow([
                'id', 'timestamp', 'user', 'action',
                'model_name', 'object_pk', 'ip_address', 'message',
            ])
            for row in qs.iterator():
                writer.writerow([
                    row.pk,
                    row.timestamp.isoformat(),
                    row.user.username if row.user else '',
                    row.action,
                    row.model_name,
                    row.object_pk,
                    row.ip_address,
                    row.message,
                ])
                count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Exported {count} audit log record(s) to {out_path}.'
        ))
        log_system_event(
            'COMMAND', 'audit_export',
            message=f'Exported {count} AuditLog records to {out_path}.',
            records=count, output=out_path,
            days=options.get('days'), action=options.get('action'), user=options.get('user'),
        )
