"""
Migration 0027: Add ActivityLog model for request-level activity tracking.

Records every HTTP request (who, what, when, where, how long) to give admins
a complete picture of all app activity — page visits, form submissions,
searches, logins, errors, and response times.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0026_systemsettings_rifle_magazine_default_limit'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ActivityLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_key', models.CharField(blank=True, max_length=40, help_text='Django session key.')),
                ('method', models.CharField(
                    max_length=6,
                    choices=[
                        ('GET', 'GET'), ('POST', 'POST'), ('PUT', 'PUT'),
                        ('PATCH', 'PATCH'), ('DELETE', 'DELETE'),
                        ('HEAD', 'HEAD'), ('OTHER', 'OTHER'),
                    ],
                    default='GET',
                )),
                ('path', models.CharField(max_length=2048, help_text='Request path.')),
                ('query_string', models.TextField(blank=True, help_text='Raw query string.')),
                ('view_name', models.CharField(blank=True, max_length=255, help_text='Resolved URL name.')),
                ('referer', models.CharField(blank=True, max_length=2048, help_text='HTTP Referer header.')),
                ('status_code', models.PositiveSmallIntegerField(blank=True, null=True, help_text='HTTP response status code.')),
                ('response_ms', models.PositiveIntegerField(blank=True, null=True, help_text='Response time in milliseconds.')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, max_length=512)),
                ('timestamp', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('user', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='activity_logs',
                    to=settings.AUTH_USER_MODEL,
                    help_text='Authenticated user; null for anonymous.',
                )),
            ],
            options={
                'verbose_name': 'Activity Log',
                'verbose_name_plural': 'Activity Logs',
                'ordering': ['-timestamp'],
            },
        ),
        migrations.AddIndex(
            model_name='activitylog',
            index=models.Index(fields=['user', '-timestamp'], name='actlog_user_ts_idx'),
        ),
        migrations.AddIndex(
            model_name='activitylog',
            index=models.Index(fields=['path', '-timestamp'], name='actlog_path_ts_idx'),
        ),
        migrations.AddIndex(
            model_name='activitylog',
            index=models.Index(fields=['status_code', '-timestamp'], name='actlog_status_ts_idx'),
        ),
    ]
