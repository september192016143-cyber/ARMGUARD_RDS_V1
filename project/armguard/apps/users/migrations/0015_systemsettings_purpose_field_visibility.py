from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0014_remove_systemsettings_app_icon'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_duty_sentinel_show_pistol',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_duty_sentinel_show_rifle',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_duty_vigil_show_pistol',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_duty_vigil_show_rifle',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_duty_security_show_pistol',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_duty_security_show_rifle',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_honor_guard_show_pistol',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_honor_guard_show_rifle',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_others_show_pistol',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_others_show_rifle',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_orex_show_pistol',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='purpose_orex_show_rifle',
            field=models.BooleanField(default=True),
        ),
    ]
