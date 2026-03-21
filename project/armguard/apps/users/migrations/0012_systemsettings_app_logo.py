from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0011_per_user_require_2fa'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='app_logo',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='site/',
                help_text='Custom logo displayed in the sidebar. Recommended: square PNG, at least 80×80 px.',
            ),
        ),
    ]
