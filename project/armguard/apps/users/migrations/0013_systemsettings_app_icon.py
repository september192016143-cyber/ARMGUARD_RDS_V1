from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0012_systemsettings_app_logo'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='app_icon',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Font Awesome icon class (e.g. "fa-solid fa-shield-halved"). Used in the sidebar when no logo image is set.',
                max_length=100,
            ),
        ),
    ]
