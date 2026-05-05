"""
Management command: simulate_orex
==================================
Simulates a realistic OREX mass-withdrawal scenario using real Personnel and
Rifle records already in the database.

Usage (dry-run, default):
    python manage.py simulate_orex

Usage (actually write transactions):
    python manage.py simulate_orex --commit

Options:
    --count N     Number of personnel to process (default: 114)
    --delay N     Seconds to wait between each transaction (default: 5)
    --commit      Write transactions to the database (default is dry-run)
    --operator U  Username to stamp on transaction_personnel (default: 'sim_operator')

What it does:
  1. Queries up to --count Active personnel (ordered by Personnel_ID).
  2. Queries Available rifles with no open discrepancy.
  3. Pairs each personnel (who has no rifle currently issued) with one rifle.
  4. Builds a Transaction(Withdrawal, TR, OREX, rifle=...) and validates it.
  5. Saves it (only when --commit is passed).
  6. Waits --delay seconds before the next transaction.
  7. Prints a summary table and timing stats at the end.

Safe to run repeatedly in dry-run mode — nothing is written without --commit.
Never touches pistol/magazine/ammo/accessory pools — rifle-only OREX withdrawal.
"""
import time

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = 'Simulate OREX rifle withdrawal for up to 114 personnel (dry-run by default).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count', type=int, default=114,
            help='Number of personnel to process (default: 114).',
        )
        parser.add_argument(
            '--delay', type=float, default=5.0,
            help='Seconds to wait between each transaction (default: 5).',
        )
        parser.add_argument(
            '--commit', action='store_true', default=False,
            help='Actually write transactions. Without this flag, nothing is saved.',
        )
        parser.add_argument(
            '--operator', type=str, default='sim_operator',
            help='Username to stamp on transaction_personnel (default: sim_operator).',
        )

    def handle(self, *args, **options):
        from armguard.apps.personnel.models import Personnel
        from armguard.apps.inventory.models import Rifle
        from armguard.apps.transactions.models import Transaction

        count    = options['count']
        delay    = options['delay']
        commit   = options['commit']
        operator = options['operator']

        self.stdout.write('')
        self.stdout.write(self.style.WARNING('=' * 62))
        self.stdout.write(self.style.WARNING('  OREX WITHDRAWAL SIMULATION'))
        self.stdout.write(self.style.WARNING('=' * 62))
        self.stdout.write(f'  Mode     : {"LIVE (--commit)" if commit else "DRY-RUN (read-only)"}')
        self.stdout.write(f'  Personnel: up to {count}')
        self.stdout.write(f'  Delay    : {delay}s between transactions')
        self.stdout.write(f'  Operator : {operator}')
        self.stdout.write(self.style.WARNING('=' * 62))
        self.stdout.write('')

        if commit:
            self.stdout.write(
                self.style.ERROR('  WARNING: --commit is set. Real transactions will be written.')
            )
            self.stdout.write('  Press Ctrl+C within 5 seconds to abort...')
            try:
                time.sleep(5)
            except KeyboardInterrupt:
                self.stdout.write(self.style.SUCCESS('\n  Aborted.'))
                return

        # ── 1. Load personnel who don't already have a rifle issued ──────────
        personnel_qs = (
            Personnel.objects
            .filter(status='Active', rifle_item_issued__isnull=True)
            .order_by('Personnel_ID')
            [:count]
        )
        personnel_list = list(personnel_qs)

        if not personnel_list:
            raise CommandError(
                'No Active personnel without a rifle found in the database. '
                'Run a truncation first or check personnel status.'
            )

        # ── 2. Load available rifles ──────────────────────────────────────────
        # Only rifles with item_status=Available and no open FirearmDiscrepancy.
        from armguard.apps.inventory.models import FirearmDiscrepancy
        discrepant_rifle_ids = set(
            FirearmDiscrepancy.objects
            .filter(rifle__isnull=False, status='Open')
            .values_list('rifle_id', flat=True)
        )
        available_rifles = list(
            Rifle.objects
            .filter(item_status='Available')
            .exclude(item_id__in=discrepant_rifle_ids)
            .order_by('item_number')
        )

        if not available_rifles:
            raise CommandError(
                'No Available rifles found in the database. '
                'Check inventory or run a truncation first.'
            )

        # ── 3. Pair personnel ↔ rifles ────────────────────────────────────────
        pairs = list(zip(personnel_list, available_rifles))
        if len(pairs) < len(personnel_list):
            self.stdout.write(
                self.style.WARNING(
                    f'  Note: only {len(available_rifles)} available rifle(s) for '
                    f'{len(personnel_list)} personnel. '
                    f'{len(personnel_list) - len(pairs)} personnel will be skipped.'
                )
            )

        total      = len(pairs)
        ok_count   = 0
        skip_count = 0
        err_count  = 0
        results    = []   # list of (idx, personnel_id, rifle_id, status, note)
        start_time = time.perf_counter()

        self.stdout.write(f'  Processing {total} transaction(s)...\n')

        for idx, (person, rifle) in enumerate(pairs, start=1):
            txn_start = time.perf_counter()

            # Build the transaction object (not yet saved)
            return_by = timezone.now() + __import__('datetime').timedelta(hours=24)
            txn = Transaction(
                transaction_type='Withdrawal',
                issuance_type='TR (Temporary Receipt)',
                purpose='OREX',
                personnel=person,
                rifle=rifle,
                transaction_personnel=operator,
                return_by=return_by,
            )

            # Validate
            try:
                txn.full_clean()
            except ValidationError as exc:
                err_count += 1
                note = '; '.join(
                    msg
                    for msgs in exc.message_dict.values()
                    for msg in msgs
                ) if hasattr(exc, 'message_dict') else str(exc)
                results.append((idx, person.Personnel_ID, rifle.item_id, 'ERROR', note[:80]))
                self.stdout.write(
                    self.style.ERROR(
                        f'  [{idx:>3}/{total}] {person.Personnel_ID:<20} '
                        f'{rifle.item_id:<20} ERROR: {note[:60]}'
                    )
                )
                # Still wait the delay so timing simulation is accurate
                elapsed = time.perf_counter() - txn_start
                remaining = delay - elapsed
                if remaining > 0 and idx < total:
                    time.sleep(remaining)
                continue

            # Save only if --commit
            if commit:
                try:
                    txn.save(user=None)
                    ok_count += 1
                    status_label = 'SAVED'
                    note = ''
                except Exception as save_exc:
                    err_count += 1
                    status_label = 'SAVE_ERR'
                    note = str(save_exc)[:80]
                    results.append((idx, person.Personnel_ID, rifle.item_id, status_label, note))
                    self.stdout.write(
                        self.style.ERROR(
                            f'  [{idx:>3}/{total}] {person.Personnel_ID:<20} '
                            f'{rifle.item_id:<20} SAVE ERROR: {note[:50]}'
                        )
                    )
                    elapsed = time.perf_counter() - txn_start
                    remaining = delay - elapsed
                    if remaining > 0 and idx < total:
                        time.sleep(remaining)
                    continue
            else:
                ok_count += 1
                status_label = 'DRY-OK'
                note = ''

            results.append((idx, person.Personnel_ID, rifle.item_id, status_label, note))
            self.stdout.write(
                self.style.SUCCESS(
                    f'  [{idx:>3}/{total}] {person.Personnel_ID:<20} '
                    f'{rifle.item_id:<20} {status_label}'
                )
            )

            # Wait for the remainder of the target delay window
            elapsed = time.perf_counter() - txn_start
            remaining = delay - elapsed
            if remaining > 0 and idx < total:
                time.sleep(remaining)

        # ── 4. Summary ────────────────────────────────────────────────────────
        wall_time   = time.perf_counter() - start_time
        avg_per_txn = wall_time / total if total else 0

        self.stdout.write('')
        self.stdout.write(self.style.WARNING('=' * 62))
        self.stdout.write(self.style.WARNING('  SIMULATION SUMMARY'))
        self.stdout.write(self.style.WARNING('=' * 62))
        self.stdout.write(f'  Total pairs     : {total}')
        self.stdout.write(
            self.style.SUCCESS(f'  Successful      : {ok_count}')
            if ok_count else f'  Successful      : {ok_count}'
        )
        if skip_count:
            self.stdout.write(f'  Skipped         : {skip_count}')
        if err_count:
            self.stdout.write(self.style.ERROR(f'  Errors          : {err_count}'))
        self.stdout.write(f'  Wall time       : {wall_time:.1f}s')
        self.stdout.write(f'  Avg per txn     : {avg_per_txn:.2f}s  (target: {delay}s)')
        self.stdout.write(f'  Committed to DB : {"YES" if commit else "NO — use --commit to save"}')

        if err_count:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR('  Errors detail:'))
            for idx, pid, rid, status, note in results:
                if status in ('ERROR', 'SAVE_ERR'):
                    self.stdout.write(self.style.ERROR(f'    [{idx:>3}] {pid} / {rid}: {note}'))

        self.stdout.write(self.style.WARNING('=' * 62))
        self.stdout.write('')

        if not commit:
            self.stdout.write(
                self.style.WARNING(
                    '  Dry-run complete. Re-run with --commit to write transactions.'
                )
            )
            self.stdout.write('')
