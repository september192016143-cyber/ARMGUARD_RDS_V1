# Backfill return_by = timestamp + 24h for all TR withdrawals that have no return_by set.

from datetime import timedelta
from django.db import migrations


def backfill_tr_return_by(apps, schema_editor):
    Transaction = apps.get_model('transactions', 'Transaction')
    qs = Transaction.objects.filter(
        transaction_type='Withdrawal',
        issuance_type__contains='TR',
        return_by__isnull=True,
    )
    for txn in qs:
        txn.return_by = txn.timestamp + timedelta(hours=24)
    Transaction.objects.bulk_update(qs, ['return_by'])


def reverse_backfill(apps, schema_editor):
    # Non-destructive reverse: leave return_by values as-is
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0004_add_return_by_to_transaction'),
    ]

    operations = [
        migrations.RunPython(backfill_tr_return_by, reverse_backfill),
    ]
