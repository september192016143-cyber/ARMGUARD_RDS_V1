# Generated manually — adds file_purged_at to CameraUploadLog and makes
# file_path nullable (blank=True) so purged records can clear the path.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('camera', '0004_alter_cameradevice_current_pin'),
    ]

    operations = [
        migrations.AddField(
            model_name='camerauploadlog',
            name='file_purged_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text='Set when the image file is deleted from disk (after 5 days). '
                          'Null means the file still exists.',
            ),
        ),
        migrations.AlterField(
            model_name='camerauploadlog',
            name='file_path',
            field=models.CharField(blank=True, max_length=512),
        ),
    ]
