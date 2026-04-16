from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0022_systemsettings_per_purpose_bandoleer'),
    ]

    operations = [
        # Rename existing rifle_mag_qty → rifle_short_mag_qty (preserves data)
        migrations.RenameField(
            model_name='systemsettings',
            old_name='duty_sentinel_rifle_mag_qty',
            new_name='duty_sentinel_rifle_short_mag_qty',
        ),
        migrations.RenameField(
            model_name='systemsettings',
            old_name='duty_vigil_rifle_mag_qty',
            new_name='duty_vigil_rifle_short_mag_qty',
        ),
        migrations.RenameField(
            model_name='systemsettings',
            old_name='duty_security_rifle_mag_qty',
            new_name='duty_security_rifle_short_mag_qty',
        ),
        migrations.RenameField(
            model_name='systemsettings',
            old_name='honor_guard_rifle_mag_qty',
            new_name='honor_guard_rifle_short_mag_qty',
        ),
        migrations.RenameField(
            model_name='systemsettings',
            old_name='others_rifle_mag_qty',
            new_name='others_rifle_short_mag_qty',
        ),
        migrations.RenameField(
            model_name='systemsettings',
            old_name='orex_rifle_mag_qty',
            new_name='orex_rifle_short_mag_qty',
        ),
        # Add new rifle_long_mag_qty fields
        migrations.AddField(
            model_name='systemsettings',
            name='duty_sentinel_rifle_long_mag_qty',
            field=models.PositiveSmallIntegerField(default=7, help_text='Rifle Long (30-rd) magazines auto-issued per Duty Sentinel withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_vigil_rifle_long_mag_qty',
            field=models.PositiveSmallIntegerField(default=7, help_text='Rifle Long (30-rd) magazines auto-issued per Duty Vigil withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_security_rifle_long_mag_qty',
            field=models.PositiveSmallIntegerField(default=7, help_text='Rifle Long (30-rd) magazines auto-issued per Duty Security withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='honor_guard_rifle_long_mag_qty',
            field=models.PositiveSmallIntegerField(default=7, help_text='Rifle Long (30-rd) magazines auto-issued per Honor Guard withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='others_rifle_long_mag_qty',
            field=models.PositiveSmallIntegerField(default=7, help_text='Rifle Long (30-rd) magazines auto-issued per Others withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='orex_rifle_long_mag_qty',
            field=models.PositiveSmallIntegerField(default=7, help_text='Rifle Long (30-rd) magazines auto-issued per OREX withdrawal.'),
        ),
    ]
