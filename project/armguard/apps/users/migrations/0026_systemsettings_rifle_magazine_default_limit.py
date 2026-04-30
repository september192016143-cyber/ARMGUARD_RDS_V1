"""
Set rifle_magazine_max_qty default to 2.

Previously the field had no default (null=True, blank=True with no default),
which caused Transaction.clean() to silently skip the per-withdrawal rifle
magazine quantity cap because _get_magazine_max_qty() returned None for 'Rifle'
and the validation guard `if max_mag and ...` evaluated to False.

This migration:
  1. Adds default=2 to the field definition.
  2. Backfills all existing rows where rifle_magazine_max_qty IS NULL to 2
     so that live installations are protected immediately without requiring
     an admin to manually set the value in System Settings.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0025_merge_20260428_2327'),
    ]

    operations = [
        # Step 1: backfill existing NULL rows so the live singleton gets the default.
        migrations.RunSQL(
            sql="UPDATE users_systemsettings SET rifle_magazine_max_qty = 2 WHERE rifle_magazine_max_qty IS NULL;",
            reverse_sql="UPDATE users_systemsettings SET rifle_magazine_max_qty = NULL WHERE rifle_magazine_max_qty = 2;",
        ),
        # Step 2: update the field metadata (adds default=2 to the column definition).
        migrations.AlterField(
            model_name='systemsettings',
            name='rifle_magazine_max_qty',
            field=models.PositiveSmallIntegerField(
                default=2,
                null=True,
                blank=True,
                help_text='Maximum rifle magazines per withdrawal (default: 2). Leave blank to use system default.',
            ),
        ),
    ]
