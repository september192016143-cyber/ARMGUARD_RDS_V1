from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('camera', '0005_camerauploadlog_file_purged_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='cameradevice',
            name='pending_serial_task',
            field=models.UUIDField(
                blank=True,
                null=True,
                editable=False,
                help_text='Token of a pending SerialImageCapture session. '
                          'Set when admin clicks \'Via Phone\' on the item form. '
                          'Cleared after the phone uploads the photo.',
            ),
        ),
    ]
