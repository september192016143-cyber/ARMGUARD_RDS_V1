"""
Data migration: seed the three default magazine pool records.

These are shared pool objects (not individual magazines) that Transactions FK into.
Each pool tracks a total stock count; individual withdrawals/returns adjust quantity.

  Pistol magazine pool — type='Pistol Standard', weapon_type='Pistol'
  Rifle magazine Short — type='Short',           weapon_type='Rifle'  (20-round)
  Rifle magazine Long  — type='Long',            weapon_type='Rifle'  (30-round)

If a record with the same type already exists it is left untouched (idempotent).
Quantity is set to 1 as a placeholder; operators should update it to reflect actual stock.
"""
from django.db import migrations


def seed_magazine_pools(apps, schema_editor):
    Magazine = apps.get_model('inventory', 'Magazine')
    defaults = [
        {'type': 'Pistol Standard', 'weapon_type': 'Pistol', 'capacity': 'Standard', 'quantity': 1},
        {'type': 'Short',           'weapon_type': 'Rifle',  'capacity': '20-rounds', 'quantity': 1},
        {'type': 'Long',            'weapon_type': 'Rifle',  'capacity': '30-rounds', 'quantity': 1},
    ]
    for d in defaults:
        Magazine.objects.get_or_create(
            type=d['type'],
            defaults={
                'weapon_type': d['weapon_type'],
                'capacity':    d['capacity'],
                'quantity':    d['quantity'],
            },
        )


def reverse_seed(apps, schema_editor):
    # Do not delete on reverse — operator may have adjusted quantities.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0002_g8_db_constraints'),
    ]

    operations = [
        migrations.RunPython(seed_magazine_pools, reverse_code=reverse_seed),
    ]
