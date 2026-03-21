from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0013_systemsettings_app_icon'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='systemsettings',
            name='app_icon',
        ),
    ]
