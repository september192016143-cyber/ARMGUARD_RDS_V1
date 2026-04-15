from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0019_auto_print_tr_per_purpose'),
    ]

    operations = [
        # ── Per-purpose consumables (3 new: Sentinel / Security / OREX) ──────
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_duty_sentinel_auto_consumables',
            field=models.BooleanField(default=True, help_text='Auto-assign magazines & ammunition for Duty Sentinel withdrawals.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_duty_security_auto_consumables',
            field=models.BooleanField(default=True, help_text='Auto-assign magazines & ammunition for Duty Security withdrawals.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_orex_auto_consumables',
            field=models.BooleanField(default=True, help_text='Auto-assign magazines & ammunition for OREX withdrawals.'),
        ),
        # ── Per-purpose accessories (6 new fields) ────────────────────────────
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_duty_sentinel_auto_accessories',
            field=models.BooleanField(default=True, help_text='Auto-assign accessories for Duty Sentinel withdrawals.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_duty_vigil_auto_accessories',
            field=models.BooleanField(default=False, help_text='Auto-assign accessories for Duty Vigil withdrawals.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_duty_security_auto_accessories',
            field=models.BooleanField(default=False, help_text='Auto-assign accessories for Duty Security withdrawals.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_honor_guard_auto_accessories',
            field=models.BooleanField(default=False, help_text='Auto-assign accessories for Honor Guard withdrawals.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_others_auto_accessories',
            field=models.BooleanField(default=False, help_text='Auto-assign accessories for Others withdrawals.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_orex_auto_accessories',
            field=models.BooleanField(default=False, help_text='Auto-assign accessories for OREX withdrawals.'),
        ),
    ]
