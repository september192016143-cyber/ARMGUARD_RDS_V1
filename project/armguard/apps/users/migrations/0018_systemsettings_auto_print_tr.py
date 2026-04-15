from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0017_systemsettings_transaction_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='auto_print_tr',
            field=models.BooleanField(
                default=False,
                help_text='Automatically open the TR print page after a TR Withdrawal is saved.',
            ),
        ),
    ]
