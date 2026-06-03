from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0011_backfill_transactionlogs_issuance_type'),
    ]

    operations = [
        # Add discrepancy_items field to TransactionLogs
        migrations.AddField(
            model_name='transactionlogs',
            name='discrepancy_items',
            field=models.CharField(
                blank=True,
                help_text="Item keys closed via discrepancy (e.g. 'rifle_sling,rifle_magazine').",
                max_length=500,
                null=True,
            ),
        ),
        # Update log_status choices to include 'Closed (Discrepancy)'
        migrations.AlterField(
            model_name='transactionlogs',
            name='log_status',
            field=models.CharField(
                choices=[
                    ('Open', 'Open'),
                    ('Partially Returned', 'Partially Returned'),
                    ('Closed', 'Closed'),
                    ('Closed (Discrepancy)', 'Closed (Discrepancy)'),
                ],
                default='Open',
                help_text='Open: not yet returned. Partially Returned: one of two items returned. Closed: all items returned.',
                max_length=20,
            ),
        ),
    ]
