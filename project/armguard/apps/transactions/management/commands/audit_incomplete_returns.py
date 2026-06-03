"""
Management command: audit_incomplete_returns

Identifies TransactionLogs where a firearm (pistol or rifle) has been
returned (return_pistol / return_rifle is set) but one or more of its
consumables (magazine, ammunition, holster, pouch, sling, bandoleer)
are still outstanding.

This state should not occur going forward (the binding rule in
Transaction.clean() and forms.py prevents it for new transactions, and
the admin's readonly_fields prevents it via the Django admin). Any rows
found were created before those safeguards were in place.

Usage:
    python manage.py audit_incomplete_returns
    python manage.py audit_incomplete_returns --csv > orphaned_logs.csv
"""

import csv
import sys
from django.core.management.base import BaseCommand
from django.db.models import Q


class Command(BaseCommand):
    help = (
        "List TransactionLogs where a firearm was returned but one or more "
        "consumables/accessories are still outstanding."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv',
            action='store_true',
            default=False,
            help='Output results in CSV format (suitable for piping to a file).',
        )

    def handle(self, *args, **options):
        from armguard.apps.transactions.models import TransactionLogs

        # ── Pistol returned but consumables still open ────────────────────────
        pistol_orphaned = TransactionLogs.objects.filter(
            return_pistol__isnull=False,           # pistol was returned
            log_status__in=['Open', 'Partially Returned'],
        ).filter(
            # At least one consumable still outstanding
            Q(withdraw_pistol_magazine__isnull=False, return_pistol_magazine__isnull=True)
            | Q(withdraw_pistol_ammunition__isnull=False, return_pistol_ammunition__isnull=True)
            | Q(withdraw_pistol_holster_quantity__isnull=False, return_pistol_holster_quantity__isnull=True)
            | Q(withdraw_magazine_pouch_quantity__isnull=False, return_magazine_pouch_quantity__isnull=True)
        ).select_related(
            'personnel_id',
            'withdraw_pistol',
            'return_pistol',
            'withdraw_pistol_magazine',
            'withdraw_pistol_ammunition',
        ).order_by('personnel_id__last_name', 'record_id')

        # ── Rifle returned but consumables still open ─────────────────────────
        rifle_orphaned = TransactionLogs.objects.filter(
            return_rifle__isnull=False,            # rifle was returned
            log_status__in=['Open', 'Partially Returned'],
        ).filter(
            Q(withdraw_rifle_magazine__isnull=False, return_rifle_magazine__isnull=True)
            | Q(withdraw_rifle_ammunition__isnull=False, return_rifle_ammunition__isnull=True)
            | Q(withdraw_rifle_sling_quantity__isnull=False, return_rifle_sling_quantity__isnull=True)
            | Q(withdraw_bandoleer_quantity__isnull=False, return_bandoleer_quantity__isnull=True)
        ).select_related(
            'personnel_id',
            'withdraw_rifle',
            'return_rifle',
            'withdraw_rifle_magazine',
            'withdraw_rifle_ammunition',
        ).order_by('personnel_id__last_name', 'record_id')

        all_orphaned = list(pistol_orphaned) + list(rifle_orphaned)

        if not all_orphaned:
            self.stdout.write(self.style.SUCCESS(
                "No orphaned TransactionLogs found. All consumables are properly tracked."
            ))
            return

        if options['csv']:
            writer = csv.writer(sys.stdout)
            writer.writerow([
                'record_id', 'personnel_id', 'personnel_name', 'issuance_type',
                'log_status', 'returned_firearm', 'outstanding_items',
            ])
            for log in all_orphaned:
                p = log.personnel_id
                pname = f"{p.rank} {p.first_name} {p.last_name}".strip() if p else 'Unknown'
                outstanding = _outstanding_items(log)
                firearm = (
                    f"Pistol {log.return_pistol}" if log.return_pistol_id
                    else f"Rifle {log.return_rifle}" if log.return_rifle_id
                    else ''
                )
                writer.writerow([
                    log.record_id, p.Personnel_ID if p else '', pname,
                    log.issuance_type or '', log.log_status,
                    firearm, '; '.join(outstanding),
                ])
        else:
            self.stdout.write(self.style.WARNING(
                f"\nFound {len(all_orphaned)} orphaned log(s) where a firearm was returned "
                f"but consumables/accessories are still outstanding:\n"
            ))
            for log in all_orphaned:
                p = log.personnel_id
                pname = f"{p.rank} {p.first_name} {p.last_name}".strip() if p else 'Unknown'
                pid = p.Personnel_ID if p else 'N/A'
                outstanding = _outstanding_items(log)
                firearm = (
                    f"Pistol {log.return_pistol}" if log.return_pistol_id
                    else f"Rifle {log.return_rifle}" if log.return_rifle_id
                    else ''
                )
                self.stdout.write(
                    f"  Log #{log.record_id} | {pid} {pname} | {log.issuance_type or 'N/A'} | "
                    f"Firearm returned: {firearm}\n"
                    f"    Outstanding: {', '.join(outstanding)}\n"
                )

            self.stdout.write(self.style.WARNING(
                "\nTo resolve: process a standalone Return transaction for each outstanding item.\n"
                "The transaction form supports returning accessories/magazines without a firearm.\n"
                "Use --csv to export this list to a spreadsheet.\n"
            ))


def _outstanding_items(log):
    items = []
    if log.withdraw_pistol_magazine_id and not log.return_pistol_magazine_id:
        qty = log.withdraw_pistol_magazine_quantity or '?'
        items.append(f"Pistol Mag ×{qty}")
    if log.withdraw_pistol_ammunition_id and not log.return_pistol_ammunition_id:
        qty = log.withdraw_pistol_ammunition_quantity or '?'
        items.append(f"Pistol Ammo ×{qty}")
    if (log.withdraw_pistol_holster_quantity or 0) > (log.return_pistol_holster_quantity or 0):
        have = log.return_pistol_holster_quantity or 0
        need = log.withdraw_pistol_holster_quantity or 0
        items.append(f"Pistol Holster ×{need} (returned: {have})")
    if (log.withdraw_magazine_pouch_quantity or 0) > (log.return_magazine_pouch_quantity or 0):
        have = log.return_magazine_pouch_quantity or 0
        need = log.withdraw_magazine_pouch_quantity or 0
        items.append(f"Mag Pouch ×{need} (returned: {have})")
    if log.withdraw_rifle_magazine_id and not log.return_rifle_magazine_id:
        qty = log.withdraw_rifle_magazine_quantity or '?'
        items.append(f"Rifle Mag ×{qty}")
    if log.withdraw_rifle_ammunition_id and not log.return_rifle_ammunition_id:
        qty = log.withdraw_rifle_ammunition_quantity or '?'
        items.append(f"Rifle Ammo ×{qty}")
    if (log.withdraw_rifle_sling_quantity or 0) > (log.return_rifle_sling_quantity or 0):
        have = log.return_rifle_sling_quantity or 0
        need = log.withdraw_rifle_sling_quantity or 0
        items.append(f"Rifle Sling ×{need} (returned: {have})")
    if (log.withdraw_bandoleer_quantity or 0) > (log.return_bandoleer_quantity or 0):
        have = log.return_bandoleer_quantity or 0
        need = log.withdraw_bandoleer_quantity or 0
        items.append(f"Bandoleer ×{need} (returned: {have})")
    return items
