from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Add image_2 through image_5 to FirearmDiscrepancy for multi-photo evidence.
    """

    dependencies = [
        ('inventory', '0010_firearmdiscrepancy_add_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='firearmdiscrepancy',
            name='image_2',
            field=models.ImageField(blank=True, null=True, upload_to='discrepancy_images/'),
        ),
        migrations.AddField(
            model_name='firearmdiscrepancy',
            name='image_3',
            field=models.ImageField(blank=True, null=True, upload_to='discrepancy_images/'),
        ),
        migrations.AddField(
            model_name='firearmdiscrepancy',
            name='image_4',
            field=models.ImageField(blank=True, null=True, upload_to='discrepancy_images/'),
        ),
        migrations.AddField(
            model_name='firearmdiscrepancy',
            name='image_5',
            field=models.ImageField(blank=True, null=True, upload_to='discrepancy_images/'),
        ),
    ]
