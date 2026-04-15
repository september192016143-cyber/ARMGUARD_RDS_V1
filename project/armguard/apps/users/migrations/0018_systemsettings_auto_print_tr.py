from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0017_systemsettings_transaction_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='auto_print_tr_duty_sentinel',
            field=models.BooleanField(default=False, help_text='Auto-print TR for Duty Sentinel withdrawals.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='auto_print_tr_duty_vigil',
            field=models.BooleanField(default=False, help_text='Auto-print TR for Duty Vigil withdrawals.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='auto_print_tr_duty_security',
            field=models.BooleanField(default=False, help_text='Auto-print TR for Duty Security withdrawals.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='auto_print_tr_honor_guard',
            field=models.BooleanField(default=False, help_text='Auto-print TR for Honor Guard withdrawals.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='auto_print_tr_others',
            field=models.BooleanField(default=False, help_text='Auto-print TR for Others withdrawals.'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='auto_print_tr_orex',
            field=models.BooleanField(default=False, help_text='Auto-print TR for OREX withdrawals.'),
        ),
    ]
