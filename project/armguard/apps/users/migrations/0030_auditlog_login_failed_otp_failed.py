"""
Migration 0030: Add LOGIN_FAILED and OTP_FAILED choices to AuditLog.action.

These two new action values are now emitted by:
  - on_user_login_failed()  → LOGIN_FAILED  (wrong password / unknown username)
  - AuditLog written in OTPVerifyView when token is invalid → OTP_FAILED

No DB schema change — CharField choices are Python-level only.
This AlterField exists solely so makemigrations on the server sees no delta.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0029_fix_activitylog_index_names'),
    ]

    operations = [
        migrations.AlterField(
            model_name='auditlog',
            name='action',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('CREATE',       'Create'),
                    ('UPDATE',       'Update'),
                    ('DELETE',       'Delete'),
                    ('LOGIN',        'Login'),
                    ('LOGOUT',       'Logout'),
                    ('LOGIN_FAILED', 'Login Failed'),
                    ('OTP_FAILED',   'OTP Failed'),
                    ('OTHER',        'Other'),
                ],
            ),
        ),
    ]
