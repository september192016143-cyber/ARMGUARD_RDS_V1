"""
Migration: update Magazine.type field choices and increase max_length from 30 to 50.

The magazine type naming convention was updated from short codes ('Pistol Standard',
'Short', 'Long') to full descriptive names (e.g. 'Mag Assy, 9mm: Glock 17').
The longest new type value is 35 characters, so max_length is raised to 50.

NOTE: This migration only updates the schema (choices + max_length).
If your database already has Magazine records with the OLD type values
('Pistol Standard', 'Short', 'Long'), run the following SQL to rename them:

    UPDATE inventory_magazine SET type='Mag Assy, 9mm: Glock 17',  weapon_type='Pistol', capacity='Standard'  WHERE type='Pistol Standard';
    UPDATE inventory_magazine SET type='Mag Assy, 5.56mm: 20 rds Cap Alloy', weapon_type='Rifle', capacity='20-rounds' WHERE type='Short';
    UPDATE inventory_magazine SET type='Mag Assy, 5.56mm: 30 rds Cap Alloy', weapon_type='Rifle', capacity='30-rounds' WHERE type='Long';

Or run manage.py shell and execute the data migration manually.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0014_merge_20260428_2325'),
    ]

    operations = [
        migrations.AlterField(
            model_name='magazine',
            name='type',
            field=models.CharField(
                max_length=50,
                choices=[
                    ('Mag Assy, 9mm: Glock 17', 'Mag Assy, 9mm: Glock 17'),
                    ('Mag Assy, Cal.45: 7 rds Cap', 'Mag Assy, Cal.45: 7 rds Cap'),
                    ('Mag Assy, Cal.45: 8 rds Cap', 'Mag Assy, Cal.45: 8 rds Cap'),
                    ('Mag Assy, Cal.45: Hi Cap', 'Mag Assy, Cal.45: Hi Cap'),
                    ('Mag Assy, 5.56mm: 20 rds Cap Alloy', 'Mag Assy, 5.56mm: 20 rds Cap Alloy'),
                    ('Mag Assy, 5.56mm: 30 rds Cap Alloy', 'Mag Assy, 5.56mm: 30 rds Cap Alloy'),
                    ('Mag Assy, 5.56mm: EMTAN', 'Mag Assy, 5.56mm: EMTAN'),
                    ('Mag Assy, 7.62mm: M14', 'Mag Assy, 7.62mm: M14'),
                ],
            ),
        ),
        migrations.AlterField(
            model_name='magazine',
            name='capacity',
            field=models.CharField(max_length=10, blank=True, editable=True),
        ),
    ]
