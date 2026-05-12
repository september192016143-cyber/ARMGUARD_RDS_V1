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
from django.db import transaction as db_transaction
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
    # Bug 1 fix: model FK fields are named WITH _id suffix (e.g. withdrawal_pistol_transaction_id);
    # using names WITHOUT _id caused getattr() to silently return None for every FK.
    withdrawal_transactions = {}
    fk_to_tx = [
        ('withdrawal_pistol_transaction_id',               'pistol'),
        ('withdrawal_rifle_transaction_id',                'rifle'),
        ('withdrawal_pistol_magazine_transaction_id',      'pistol_magazine'),
        ('withdrawal_rifle_magazine_transaction_id',       'rifle_magazine'),
        ('withdrawal_pistol_ammunition_transaction_id',    'pistol_ammunition'),
        ('withdrawal_rifle_ammunition_transaction_id',     'rifle_ammunition'),
        ('withdrawal_pistol_holster_transaction_id',       'pistol_holster'),
        ('withdrawal_magazine_pouch_transaction_id',       'magazine_pouch'),
        ('withdrawal_rifle_sling_transaction_id',          'rifle_sling'),
        ('withdrawal_bandoleer_transaction_id',            'bandoleer'),
    ]
    for fk_attr, _ in fk_to_tx:
        tx = getattr(log_row, fk_attr, None)
        if tx is not None and tx.transaction_type == 'Withdrawal':
            withdrawal_transactions[tx.pk] = tx

    if not withdrawal_transactions:
        return False

    # Bug 2 fix: initialise all 40 consumable keys to None first, then let each
    # transaction fill in ONLY the consumable groups it actually has.  Previously
    # update_kwargs.update({all 40 keys}) was called for every tx, so the last tx
    # in the iteration overwrote all keys set by earlier txs — e.g. a rifle-only
    # tx would clear pistol-magazine data written by a preceding pistol tx.
    update_kwargs = {
        # --- Magazines ---
        'withdrawal_pistol_magazine_transaction_id':      None,
        'withdraw_pistol_magazine_id':                    None,
        'withdraw_pistol_magazine_quantity':              None,
        'withdraw_pistol_magazine_timestamp':             None,
        'withdraw_pistol_magazine_transaction_personnel': None,
        'withdrawal_rifle_magazine_transaction_id':       None,
        'withdraw_rifle_magazine_id':                     None,
        'withdraw_rifle_magazine_quantity':               None,
        'withdraw_rifle_magazine_timestamp':              None,
        'withdraw_rifle_magazine_transaction_personnel':  None,
        # --- Ammunition ---
        'withdrawal_pistol_ammunition_transaction_id':       None,
        'withdraw_pistol_ammunition_id':                     None,
        'withdraw_pistol_ammunition_quantity':               None,
        'withdraw_pistol_ammunition_timestamp':              None,
        'withdraw_pistol_ammunition_transaction_personnel':  None,
        'withdrawal_rifle_ammunition_transaction_id':        None,
        'withdraw_rifle_ammunition_id':                      None,
        'withdraw_rifle_ammunition_quantity':                None,
        'withdraw_rifle_ammunition_timestamp':               None,
        'withdraw_rifle_ammunition_transaction_personnel':   None,
        # --- Accessories ---
        'withdrawal_pistol_holster_transaction_id':       None,
        'withdraw_pistol_holster_quantity':               None,
        'withdraw_pistol_holster_timestamp':              None,
        'withdraw_pistol_holster_transaction_personnel':  None,
        'withdrawal_magazine_pouch_transaction_id':       None,
        'withdraw_magazine_pouch_quantity':               None,
        'withdraw_magazine_pouch_timestamp':              None,
        'withdraw_magazine_pouch_transaction_personnel':  None,
        'withdrawal_rifle_sling_transaction_id':          None,
        'withdraw_rifle_sling_quantity':                  None,
        'withdraw_rifle_sling_timestamp':                 None,
        'withdraw_rifle_sling_transaction_personnel':     None,
        'withdrawal_bandoleer_transaction_id':            None,
        'withdraw_bandoleer_quantity':                    None,
        'withdraw_bandoleer_timestamp':                   None,
        'withdraw_bandoleer_transaction_personnel':       None,
    }

    for tx in withdrawal_transactions.values():
        ts = tx.timestamp
        operator = tx.transaction_personnel

        # Only fill in keys for consumables THIS transaction actually has.
        # FK transaction fields use raw attname (_id suffix) so that
        # setattr + save(update_fields=[...]) resolves the correct DB column.
        # Pass tx.pk (integer), not the tx object.
        if tx.pistol_magazine_id:
            update_kwargs['withdrawal_pistol_magazine_transaction_id']      = tx.pk
            update_kwargs['withdraw_pistol_magazine_id']                    = tx.pistol_magazine_id
            update_kwargs['withdraw_pistol_magazine_quantity']              = tx.pistol_magazine_quantity
            update_kwargs['withdraw_pistol_magazine_timestamp']             = ts
            update_kwargs['withdraw_pistol_magazine_transaction_personnel'] = operator
        if tx.rifle_magazine_id:
            update_kwargs['withdrawal_rifle_magazine_transaction_id']       = tx.pk
            update_kwargs['withdraw_rifle_magazine_id']                     = tx.rifle_magazine_id
            update_kwargs['withdraw_rifle_magazine_quantity']               = tx.rifle_magazine_quantity
            update_kwargs['withdraw_rifle_magazine_timestamp']              = ts
            update_kwargs['withdraw_rifle_magazine_transaction_personnel']  = operator
        if tx.pistol_ammunition_id:
            update_kwargs['withdrawal_pistol_ammunition_transaction_id']      = tx.pk
            update_kwargs['withdraw_pistol_ammunition_id']                    = tx.pistol_ammunition_id
            update_kwargs['withdraw_pistol_ammunition_quantity']              = tx.pistol_ammunition_quantity
            update_kwargs['withdraw_pistol_ammunition_timestamp']             = ts
            update_kwargs['withdraw_pistol_ammunition_transaction_personnel'] = operator
        if tx.rifle_ammunition_id:
            update_kwargs['withdrawal_rifle_ammunition_transaction_id']       = tx.pk
            update_kwargs['withdraw_rifle_ammunition_id']                     = tx.rifle_ammunition_id
            update_kwargs['withdraw_rifle_ammunition_quantity']               = tx.rifle_ammunition_quantity
            update_kwargs['withdraw_rifle_ammunition_timestamp']              = ts
            update_kwargs['withdraw_rifle_ammunition_transaction_personnel']  = operator
        if tx.pistol_holster_quantity:
            update_kwargs['withdrawal_pistol_holster_transaction_id']       = tx.pk
            update_kwargs['withdraw_pistol_holster_quantity']               = tx.pistol_holster_quantity
            update_kwargs['withdraw_pistol_holster_timestamp']              = ts
            update_kwargs['withdraw_pistol_holster_transaction_personnel']  = operator
        if tx.magazine_pouch_quantity:
            update_kwargs['withdrawal_magazine_pouch_transaction_id']       = tx.pk
            update_kwargs['withdraw_magazine_pouch_quantity']               = tx.magazine_pouch_quantity
            update_kwargs['withdraw_magazine_pouch_timestamp']              = ts
            update_kwargs['withdraw_magazine_pouch_transaction_personnel']  = operator
        if tx.rifle_sling_quantity:
            update_kwargs['withdrawal_rifle_sling_transaction_id']          = tx.pk
            update_kwargs['withdraw_rifle_sling_quantity']                  = tx.rifle_sling_quantity
            update_kwargs['withdraw_rifle_sling_timestamp']                 = ts
            update_kwargs['withdraw_rifle_sling_transaction_personnel']     = operator
        if tx.bandoleer_quantity:
            update_kwargs['withdrawal_bandoleer_transaction_id']            = tx.pk
            update_kwargs['withdraw_bandoleer_quantity']                    = tx.bandoleer_quantity
            update_kwargs['withdraw_bandoleer_timestamp']                   = ts
            update_kwargs['withdraw_bandoleer_transaction_personnel']       = operator

    # Skip rows that are already correct.
    # FK fields whose field.name ends in _transaction_id store their raw PK
    # under field.attname = field.name + '_id' in __dict__.  getattr() on a
    # field.name returns the descriptor-resolved Transaction *object*, so
    # comparing it against an integer (tx.pk) is always True — breaking
    # idempotency.  Reading from __dict__ returns the raw integer instead.
    # Non-FK fields and FK attnames (e.g. withdraw_pistol_magazine_id) are
    # stored as-is in __dict__ so the fallback lookup covers them correctly.
    raw_cache = log_row.__dict__
    actually_changed = any(
        raw_cache.get(k + '_id', raw_cache.get(k)) != v
        for k, v in update_kwargs.items()
    )
    if not actually_changed:
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
        # Bug 1 fix: field names on TransactionLogs are withdrawal_*_transaction_id
        # (WITH _id suffix); using the name without _id raises FieldError at runtime.
        candidate_filter = (
            Q(withdrawal_pistol_transaction_id__isnull=False) |
            Q(withdrawal_rifle_transaction_id__isnull=False)
        )
        rows = (
            TransactionLogs.objects
            .filter(candidate_filter)
            .select_related(
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
            )
        )

        total = rows.count()
        updated = 0
        skipped = 0

        self.stdout.write(f'Found {total} candidate TransactionLogs row(s) to inspect.')

        with db_transaction.atomic():
            for row in rows.iterator(chunk_size=200):
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
