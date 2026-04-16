from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0021_systemsettings_per_purpose_loadout'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='duty_sentinel_bandoleer_qty',
            field=models.PositiveSmallIntegerField(default=0, help_text='Bandoleers auto-issued per Duty Sentinel withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_vigil_bandoleer_qty',
            field=models.PositiveSmallIntegerField(default=0, help_text='Bandoleers auto-issued per Duty Vigil withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='duty_security_bandoleer_qty',
            field=models.PositiveSmallIntegerField(default=0, help_text='Bandoleers auto-issued per Duty Security withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='honor_guard_bandoleer_qty',
            field=models.PositiveSmallIntegerField(default=0, help_text='Bandoleers auto-issued per Honor Guard withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='others_bandoleer_qty',
            field=models.PositiveSmallIntegerField(default=0, help_text='Bandoleers auto-issued per Others withdrawal.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='orex_bandoleer_qty',
            field=models.PositiveSmallIntegerField(default=0, help_text='Bandoleers auto-issued per OREX withdrawal.'),
        ),
    ]
