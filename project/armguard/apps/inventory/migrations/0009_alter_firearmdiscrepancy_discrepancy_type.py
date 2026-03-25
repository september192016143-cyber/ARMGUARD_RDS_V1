from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Remove 'Extra Rounds' from FirearmDiscrepancy.discrepancy_type choices.

    'Extra Rounds' is an ammunition concept and does not apply to a firearm
    discrepancy record.  This migration keeps the migration state in sync with
    the model definition so Django's migration autodetect never flags it as
    a pending change on the server (which previously caused the Pi to
    auto-generate this file locally, triggering a recurring stash-pop conflict
    on every deployment).
    """

    dependencies = [
        ('inventory', '0008_firearmdiscrepancy_fix_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='firearmdiscrepancy',
            name='discrepancy_type',
            field=models.CharField(
                max_length=50,
                choices=[
                    ('Missing',                'Missing'),
                    ('Damaged',                'Damaged'),
                    ('Wrong Serial',           'Wrong Serial'),
                    ('Condition Mismatch',     'Condition Mismatch'),
                    ('Incomplete Accessories', 'Incomplete Accessories'),
                    ('Others',                 'Others'),
                ],
            ),
        ),
    ]
