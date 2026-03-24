from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('camera', '0002_camera_device'),
    ]

    operations = [
        migrations.AddField(
            model_name='cameradevice',
            name='current_pin',
            field=models.CharField(
                blank=True,
                help_text='Current 6-digit PIN (rotates every 30 s). Empty until first generated.',
                max_length=6,
                default='',
            ),
        ),
        migrations.AddField(
            model_name='cameradevice',
            name='pin_expires_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text='When current_pin expires and must be regenerated.',
            ),
        ),
    ]
