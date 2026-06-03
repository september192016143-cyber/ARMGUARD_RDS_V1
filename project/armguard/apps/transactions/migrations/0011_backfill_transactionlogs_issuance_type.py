"""
Backfill TransactionLogs.issuance_type for any rows where it is NULL.

Rows created before the auto-copy logic in TransactionLogs.save() was added
(or before the resync signal existed) may have a NULL issuance_type even
though the linked withdrawal Transaction has one.  This migration resolves
the value from whichever withdrawal_*_transaction_id FK is populated,
matching the exact priority order used in TransactionLogs.save().
"""
from django.db import migrations


WITHDRAWAL_FK_FIELDS = [
    'withdrawal_pistol_transaction_id',
    'withdrawal_rifle_transaction_id',
    'withdrawal_pistol_magazine_transaction_id',
    'withdrawal_rifle_magazine_transaction_id',
    'withdrawal_pistol_ammunition_transaction_id',
    'withdrawal_rifle_ammunition_transaction_id',
    'withdrawal_pistol_holster_transaction_id',
    'withdrawal_magazine_pouch_transaction_id',
    'withdrawal_rifle_sling_transaction_id',
    'withdrawal_bandoleer_transaction_id',
]


def backfill_issuance_type(apps, schema_editor):
    from django.db.models import Q
    TransactionLogs = apps.get_model('transactions', 'TransactionLogs')
    # Catch both NULL and empty-string; the model save() treats both as missing.
    null_logs = TransactionLogs.objects.filter(
        Q(issuance_type__isnull=True) | Q(issuance_type='')
    )
    updated = 0
    for log in null_logs.select_related(*WITHDRAWAL_FK_FIELDS):
        for fk_attr in WITHDRAWAL_FK_FIELDS:
            txn = getattr(log, fk_attr, None)
            if txn is not None and getattr(txn, 'issuance_type', None):
                log.issuance_type = txn.issuance_type
                log.save(update_fields=['issuance_type'])
                updated += 1
                break
    if updated:
        print(f'\n  Backfilled issuance_type on {updated} TransactionLogs row(s).')


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0010_drop_txn_purpose_valid_constraint'),
    ]

    operations = [
        migrations.RunPython(backfill_issuance_type, migrations.RunPython.noop),
    ]
