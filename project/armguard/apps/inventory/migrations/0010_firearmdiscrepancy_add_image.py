from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Add optional image field to FirearmDiscrepancy for photo evidence.
    """

    dependencies = [
        ('inventory', '0009_alter_firearmdiscrepancy_discrepancy_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='firearmdiscrepancy',
            name='image',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='discrepancy_images/',
                help_text='Optional photo evidence of the discrepancy.',
            ),
        ),
    ]
