"""
Management command: backfill_transaction_logs

Resyncs magazine, ammunition, and accessory fields on existing TransactionLogs
rows that were created before the _resync_log_consumable_fields signal fix
(commit d028336).

When a Withdrawal Transaction was edited after initial creation, the linked
TransactionLogs rows were never updated with the new consumable FKs.  This
caused the dashboard ISSUED counts to show 0 for those records.

This command applies the same resync logic to every existing TransactionLogs
row that has at least one linked Withdrawal Transaction, backfilling any NULL
or stale consumable fields.

Safe to run multiple times (idempotent).

Usage:
    python manage.py backfill_transaction_logs
    python manage.py backfill_transaction_logs --dry-run
    python manage.py backfill_transaction_logs --verbosity 2
"""
import logging

from django.core.management.base import BaseCommand
from django.db.models import Q

audit_logger = logging.getLogger('armguard.audit')


def _resync_row(log_row, dry_run=False):
    """
    Inspect one TransactionLogs row, build update_kwargs from the linked
    Withdrawal Transaction(s), and apply the update.

    Returns True if the row was (or would be) updated.
    """
    # Each log row links to up to two Withdrawal transactions (pistol/rifle).
    # Collect the unique Withdrawal transactions referenced by this row.
    withdrawal_transactions = {}
    fk_to_tx = [
        ('withdrawal_pistol_transaction',               'pistol'),
        ('withdrawal_rifle_transaction',                'rifle'),
        ('withdrawal_pistol_magazine_transaction',      'pistol_magazine'),
        ('withdrawal_rifle_magazine_transaction',       'rifle_magazine'),
        ('withdrawal_pistol_ammunition_transaction',    'pistol_ammunition'),
        ('withdrawal_rifle_ammunition_transaction',     'rifle_ammunition'),
        ('withdrawal_pistol_holster_transaction',       'pistol_holster'),
        ('withdrawal_magazine_pouch_transaction',       'magazine_pouch'),
        ('withdrawal_rifle_sling_transaction',          'rifle_sling'),
        ('withdrawal_bandoleer_transaction',            'bandoleer'),
    ]
    for fk_attr, _ in fk_to_tx:
        tx = getattr(log_row, fk_attr, None)
        if tx is not None and tx.transaction_type == 'Withdrawal':
            withdrawal_transactions[tx.pk] = tx

    if not withdrawal_transactions:
        return False

    update_kwargs = {}

    for tx in withdrawal_transactions.values():
        ts = tx.timestamp

        # --- Magazines ---
        if tx.pistol_magazine_id:
            update_kwargs.update({
                'withdrawal_pistol_magazine_transaction': tx,
                'withdraw_pistol_magazine_id': tx.pistol_magazine_id,
                'withdraw_pistol_magazine_quantity': tx.pistol_magazine_quantity,
                'withdraw_pistol_magazine_timestamp': ts,
            })
        if tx.rifle_magazine_id:
            update_kwargs.update({
                'withdrawal_rifle_magazine_transaction': tx,
                'withdraw_rifle_magazine_id': tx.rifle_magazine_id,
                'withdraw_rifle_magazine_quantity': tx.rifle_magazine_quantity,
                'withdraw_rifle_magazine_timestamp': ts,
            })

        # --- Ammunition ---
        if tx.pistol_ammunition_id:
            update_kwargs.update({
                'withdrawal_pistol_ammunition_transaction': tx,
                'withdraw_pistol_ammunition_id': tx.pistol_ammunition_id,
                'withdraw_pistol_ammunition_quantity': tx.pistol_ammunition_quantity,
                'withdraw_pistol_ammunition_timestamp': ts,
            })
        if tx.rifle_ammunition_id:
            update_kwargs.update({
                'withdrawal_rifle_ammunition_transaction': tx,
                'withdraw_rifle_ammunition_id': tx.rifle_ammunition_id,
                'withdraw_rifle_ammunition_quantity': tx.rifle_ammunition_quantity,
                'withdraw_rifle_ammunition_timestamp': ts,
            })

        # --- Accessories ---
        if tx.pistol_holster_quantity:
            update_kwargs.update({
                'withdrawal_pistol_holster_transaction': tx,
                'withdraw_pistol_holster_quantity': tx.pistol_holster_quantity,
                'withdraw_pistol_holster_timestamp': ts,
            })
        if tx.magazine_pouch_quantity:
            update_kwargs.update({
                'withdrawal_magazine_pouch_transaction': tx,
                'withdraw_magazine_pouch_quantity': tx.magazine_pouch_quantity,
                'withdraw_magazine_pouch_timestamp': ts,
            })
        if tx.rifle_sling_quantity:
            update_kwargs.update({
                'withdrawal_rifle_sling_transaction': tx,
                'withdraw_rifle_sling_quantity': tx.rifle_sling_quantity,
                'withdraw_rifle_sling_timestamp': ts,
            })
        if tx.bandoleer_quantity:
            update_kwargs.update({
                'withdrawal_bandoleer_transaction': tx,
                'withdraw_bandoleer_quantity': tx.bandoleer_quantity,
                'withdraw_bandoleer_timestamp': ts,
            })

    if not update_kwargs:
        return False

    if not dry_run:
        for attr, val in update_kwargs.items():
            setattr(log_row, attr, val)
        log_row.save(update_fields=list(update_kwargs.keys()))
        audit_logger.info(
            "[AUDIT] action=BACKFILL  model=TransactionLogs  "
            "log_id=%s tx_ids=%s fields=%d",
            log_row.pk,
            list(withdrawal_transactions.keys()),
            len(update_kwargs),
        )

    return True


class Command(BaseCommand):
    help = (
        'Backfill magazine/ammo/accessory fields on TransactionLogs rows that '
        'were created before the consumable-resync signal fix.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Preview changes without writing to the database.',
        )

    def handle(self, *args, **options):
        from django.apps import apps
        TransactionLogs = apps.get_model('transactions', 'TransactionLogs')

        dry_run = options['dry_run']
        verbosity = options['verbosity']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes will be written.'))

        # Only consider log rows that have at least one linked Withdrawal Transaction
        # (i.e. at least one of the pistol/rifle transaction FKs is set).
        candidate_filter = (
            Q(withdrawal_pistol_transaction__isnull=False) |
            Q(withdrawal_rifle_transaction__isnull=False)
        )
        rows = (
            TransactionLogs.objects
            .filter(candidate_filter)
            .select_related(
                'withdrawal_pistol_transaction',
                'withdrawal_rifle_transaction',
                'withdrawal_pistol_magazine_transaction',
                'withdrawal_rifle_magazine_transaction',
                'withdrawal_pistol_ammunition_transaction',
                'withdrawal_rifle_ammunition_transaction',
                'withdrawal_pistol_holster_transaction',
                'withdrawal_magazine_pouch_transaction',
                'withdrawal_rifle_sling_transaction',
                'withdrawal_bandoleer_transaction',
            )
        )

        total = rows.count()
        updated = 0
        skipped = 0

        self.stdout.write(f'Found {total} candidate TransactionLogs row(s) to inspect.')

        for row in rows.iterator():
            changed = _resync_row(row, dry_run=dry_run)
            if changed:
                updated += 1
                if verbosity >= 2:
                    self.stdout.write(f'  {"[DRY RUN] Would update" if dry_run else "Updated"} log row id={row.pk}')
            else:
                skipped += 1
                if verbosity >= 2:
                    self.stdout.write(f'  Skipped log row id={row.pk} (no consumable fields to sync)')

        verb = 'Would update' if dry_run else 'Updated'
        self.stdout.write(
            self.style.SUCCESS(
                f'{verb} {updated} row(s); skipped {skipped} row(s) (already correct or no consumables).'
            )
        )
