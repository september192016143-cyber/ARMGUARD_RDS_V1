from django.conf import settings
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Fix FirearmDiscrepancy:
    - Remove redundant `firearm_type` CharField (now a @property on the model).
    - Replace `reported_by` / `resolved_by` CharFields with FKs to AUTH_USER_MODEL.
    """

    dependencies = [
        ('inventory', '0007_serial_image_capture'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Drop the redundant firearm_type field.
        migrations.RemoveField(
            model_name='firearmdiscrepancy',
            name='firearm_type',
        ),

        # 2. reported_by: CharField → FK
        migrations.RemoveField(
            model_name='firearmdiscrepancy',
            name='reported_by',
        ),
        migrations.AddField(
            model_name='firearmdiscrepancy',
            name='reported_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='discrepancies_reported',
                to=settings.AUTH_USER_MODEL,
                help_text='User who reported this discrepancy.',
            ),
        ),

        # 3. resolved_by: CharField → FK
        migrations.RemoveField(
            model_name='firearmdiscrepancy',
            name='resolved_by',
        ),
        migrations.AddField(
            model_name='firearmdiscrepancy',
            name='resolved_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='discrepancies_resolved',
                to=settings.AUTH_USER_MODEL,
                help_text='User who resolved this discrepancy.',
            ),
        ),
    ]
