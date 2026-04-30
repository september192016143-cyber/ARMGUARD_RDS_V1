"""
Migration 0028: Extend ActivityLog for systematic review and problem detection.

New fields:
  flag             — auto-classified severity: NORMAL / SLOW / WARNING / SUSPICIOUS / ERROR
  exception_type   — Python exception class name on uncaught 5xx
  exception_message — exception text
  search_query     — extracted ?q= / ?search= / ?query= value
  index on (flag, -timestamp) for fast admin filtering
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0027_activitylog'),
    ]

    operations = [
        migrations.AddField(
            model_name='activitylog',
            name='flag',
            field=models.CharField(
                max_length=12,
                choices=[
                    ('NORMAL',     'Normal'),
                    ('SLOW',       'Slow  (> 2 s)'),
                    ('WARNING',    'Warning  (404)'),
                    ('SUSPICIOUS', 'Suspicious  (401 / 403)'),
                    ('ERROR',      'Error  (5xx / exception)'),
                ],
                default='NORMAL',
                db_index=True,
                help_text='Auto-classified severity of this request.',
            ),
        ),
        migrations.AddField(
            model_name='activitylog',
            name='exception_type',
            field=models.CharField(
                max_length=200, blank=True,
                help_text="Python exception class name captured before Django's 500 handler ran.",
            ),
        ),
        migrations.AddField(
            model_name='activitylog',
            name='exception_message',
            field=models.TextField(
                blank=True,
                help_text='Exception message text.',
            ),
        ),
        migrations.AddField(
            model_name='activitylog',
            name='search_query',
            field=models.CharField(
                max_length=500, blank=True, db_index=True,
                help_text='Value of ?q=, ?search=, or ?query= param.',
            ),
        ),
        migrations.AddIndex(
            model_name='activitylog',
            index=models.Index(fields=['flag', '-timestamp'], name='actlog_flag_ts_idx'),
        ),
    ]
