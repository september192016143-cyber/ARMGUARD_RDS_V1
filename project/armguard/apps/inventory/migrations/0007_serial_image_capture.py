import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0006_alter_firearmdiscrepancy_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='SerialImageCapture',
            fields=[
                ('token', models.UUIDField(
                    default=uuid.uuid4,
                    editable=False,
                    primary_key=True,
                    serialize=False,
                )),
                ('image', models.ImageField(
                    blank=True,
                    null=True,
                    upload_to='serial_capture_temp/',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Serial Image Capture Session',
            },
        ),
    ]
