"""
0005_remove_group_choices

Remove the static choices= constraint from Personnel.group so that
Django's full_clean() (called inside ModelForm._post_clean()) no longer
rejects group values that exist in the PersonnelGroup DB table but are
not in the legacy static list.

Also upgrades PersonnelGroup.id from AutoField to BigAutoField to match
the project DEFAULT_AUTO_FIELD setting and prevent Django from
auto-generating this migration on the server.

Both operations are schema-level no-ops on SQLite / PostgreSQL — no data
is modified and no table columns are added or removed.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('personnel', '0004_personnelgroup'),
    ]

    operations = [
        # Fix AutoField -> BigAutoField drift on PersonnelGroup (stops the
        # server from auto-generating its own 0005 migration every deploy).
        migrations.AlterField(
            model_name='personnelgroup',
            name='id',
            field=models.BigAutoField(
                auto_created=True,
                primary_key=True,
                serialize=False,
                verbose_name='ID',
            ),
        ),
        # Remove static choices from Personnel.group.
        # Validation is now handled entirely by PersonnelForm (DB-backed
        # PersonnelGroup choices) so the model field needs no choices list.
        migrations.AlterField(
            model_name='personnel',
            name='group',
            field=models.CharField(max_length=50),
        ),
    ]
