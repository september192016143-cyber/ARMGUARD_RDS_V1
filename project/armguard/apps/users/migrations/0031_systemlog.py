"""
Migration 0031: Add SystemLog model.

SystemLog records system-level events that are not tied to a specific user
HTTP request:
  - Application startup (STARTUP / app_ready)
  - Database backup creation, rotation, and failure (BACKUP)
  - DB schema migrations applied (MIGRATION)
  - Expired-session cleanup jobs (SESSION)
  - Management command executions (COMMAND)
  - Cache backend errors (CACHE)
  - Email send success / failure (EMAIL)
  - File system operations (FILE)
  - Scheduled / cron task runs (SCHEDULER)
  - Any other automated background events (OTHER)

Use log_system_event() from armguard.apps.users.models to write records.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0030_auditlog_login_failed_otp_failed'),
    ]

    operations = [
        migrations.CreateModel(
            name='SystemLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('level', models.CharField(
                    max_length=8,
                    choices=[
                        ('INFO',     'Info'),
                        ('WARNING',  'Warning'),
                        ('ERROR',    'Error'),
                        ('CRITICAL', 'Critical'),
                    ],
                    default='INFO',
                    db_index=True,
                    help_text='Severity of the event.',
                )),
                ('source', models.CharField(
                    max_length=10,
                    choices=[
                        ('STARTUP',   'Application Startup'),
                        ('BACKUP',    'Database Backup'),
                        ('MIGRATION', 'DB Migration'),
                        ('SESSION',   'Session Cleanup'),
                        ('COMMAND',   'Management Command'),
                        ('CACHE',     'Cache Backend'),
                        ('EMAIL',     'Email / Notification'),
                        ('FILE',      'File System'),
                        ('SCHEDULER', 'Scheduled Task'),
                        ('OTHER',     'Other'),
                    ],
                    default='OTHER',
                    db_index=True,
                    help_text='Subsystem that generated this event.',
                )),
                ('event', models.CharField(
                    max_length=80,
                    blank=True,
                    db_index=True,
                    help_text='Short machine-readable identifier, e.g. backup_created, sessions_cleaned.',
                )),
                ('message', models.TextField(
                    blank=True,
                    help_text='Human-readable description of what happened.',
                )),
                ('detail', models.JSONField(
                    default=dict,
                    blank=True,
                    help_text='Structured metadata (row counts, file sizes, tracebacks, etc.).',
                )),
                ('timestamp', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'verbose_name': 'System Log',
                'verbose_name_plural': 'System Logs',
                'ordering': ['-timestamp'],
            },
        ),
        migrations.AddIndex(
            model_name='systemlog',
            index=models.Index(fields=['level', '-timestamp'], name='users_sysl_level_ts_idx'),
        ),
        migrations.AddIndex(
            model_name='systemlog',
            index=models.Index(fields=['source', '-timestamp'], name='users_sysl_source_ts_idx'),
        ),
    ]
