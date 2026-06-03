from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0012_add_property_number'),
    ]

    operations = [
        migrations.AddField(
            model_name='firearmdiscrepancy',
            name='accessory_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('Pistol Magazine', 'Pistol Magazine'),
                    ('Pistol Ammunition', 'Pistol Ammunition'),
                    ('Pistol Holster', 'Pistol Holster'),
                    ('Magazine Pouch', 'Magazine Pouch'),
                    ('Rifle Magazine', 'Rifle Magazine'),
                    ('Rifle Ammunition', 'Rifle Ammunition'),
                    ('Rifle Sling', 'Rifle Sling'),
                    ('Bandoleer', 'Bandoleer'),
                ],
                help_text='Set when the discrepancy relates to a consumable/accessory rather than the firearm itself.',
                max_length=50,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='firearmdiscrepancy',
            name='accessory_quantity',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Quantity of the consumable that is discrepant.',
                null=True,
            ),
        ),
        # Update pistol/rifle FK constraints to allow null so that accessory-only
        # discrepancy records (no firearm FK) can be saved.
        # The model's clean() now allows accessory_type as a valid alternative.
    ]
