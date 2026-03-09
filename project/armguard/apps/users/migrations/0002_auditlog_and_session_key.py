"""
Migration 0002: Add AuditLog model and UserProfile.last_session_key field.

G3 FIX (§3.7 Audit trail): New AuditLog DB model for persistent audit records.
G4 FIX (§3.8 Session management): last_session_key enables single-session enforcement.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Add last_session_key to UserProfile for single-session tracking.
        migrations.AddField(
            model_name='userprofile',
            name='last_session_key',
            field=models.CharField(
                blank=True,
                max_length=40,
                null=True,
                help_text='Session key from the last successful login. Used for single-session enforcement.',
            ),
        ),
        # Create AuditLog for persistent database-backed audit trail.
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True,
                    primary_key=True,
                    serialize=False,
                    verbose_name='ID',
                )),
                ('action', models.CharField(
                    max_length=20,
                    choices=[
                        ('CREATE', 'Create'),
                        ('UPDATE', 'Update'),
                        ('DELETE', 'Delete'),
                        ('LOGIN', 'Login'),
                        ('LOGOUT', 'Logout'),
                        ('OTHER', 'Other'),
                    ],
                )),
                ('model_name', models.CharField(blank=True, max_length=100)),
                ('object_pk', models.CharField(blank=True, max_length=100)),
                ('message', models.TextField(blank=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='audit_logs',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Audit Log',
                'verbose_name_plural': 'Audit Logs',
                'ordering': ['-timestamp'],
            },
        ),
    ]
