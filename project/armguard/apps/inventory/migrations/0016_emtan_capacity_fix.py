"""
Migration: set capacity='EMTAN' for all EMTAN magazine records.

Previously, 'Mag Assy, 5.56mm: EMTAN' magazines shared capacity='30-rounds'
with 'Mag Assy, 5.56mm: 30 rds Cap Alloy'. This ambiguity caused any
filter(capacity='30-rounds') query to potentially return EMTAN magazines
for non-EMTAN rifles, leading to caliber-incompatibility errors.

This migration gives EMTAN magazines a dedicated capacity value ('EMTAN')
matching the pattern already used for 7.62mm M14 magazines ('M14').
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0015_magazine_type_refactor'),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "UPDATE inventory_magazine "
                "SET capacity='EMTAN' "
                "WHERE type='Mag Assy, 5.56mm: EMTAN';"
            ),
            reverse_sql=(
                "UPDATE inventory_magazine "
                "SET capacity='30-rounds' "
                "WHERE type='Mag Assy, 5.56mm: EMTAN';"
            ),
        ),
    ]
