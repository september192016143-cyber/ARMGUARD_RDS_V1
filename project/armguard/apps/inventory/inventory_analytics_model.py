from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator

# ---------------------------------------------------------------------------
# ISSUANCE TYPE — synced with transactions/models.py ISSUANCE_TYPE_CHOICES
# ---------------------------------------------------------------------------
ISSUANCE_TYPE_CHOICES = [
    ('PAR (Property Acknowledgement Receipt)', 'PAR (Property Acknowledgement Receipt)'),
    ('TR (Temporary Receipt)', 'TR (Temporary Receipt)'),
]

# ---------------------------------------------------------------------------
# TRANSACTION — synced with transactions/models.py
# ---------------------------------------------------------------------------
TRANSACTION_TYPE_CHOICES = [
    ('Withdrawal', 'Withdrawal'),
    ('Return', 'Return'),
]

LOG_STATUS_CHOICES = [
    ('Open', 'Open'),
    ('Partially Returned', 'Partially Returned'),
    ('Closed', 'Closed'),
]

DUTY_TYPE_CHOICES = [
    ('Duty Sentinel', 'Duty Sentinel'),
    ('Duty Vigil', 'Duty Vigil'),
    ('Duty Security', 'Duty Security'),
    ('Others', 'Others'),
]

# ---------------------------------------------------------------------------
# ITEM TYPES / CATEGORIES — synced with inventory/models.py ITEMS_CHOICES
# ---------------------------------------------------------------------------
ITEMS_CHOICES = [
    ('Small Arms', 'Small Arms'),
    ('Ammunition', 'Ammunition'),
    ('Magazines', 'Magazines'),
    ('Accessories', 'Accessories'),
]

SMALL_ARMS_CHOICES = [
    ('Pistol', 'Pistol'),
    ('Rifle', 'Rifle'),
]

# ---------------------------------------------------------------------------
# WEAPON MODELS — synced with inventory/models.py PISTOL_MODELS / RIFLE_MODELS
# ---------------------------------------------------------------------------
PISTOL_MODELS = [
    ('Glock 17 9mm', 'Glock 17 9mm'),
    ('M1911 Cal.45', 'M1911 Cal.45'),
    ('Armscor Hi Cap Cal.45', 'Armscor Hi Cap Cal.45'),
    ('RIA Hi Cap Cal.45', 'RIA Hi Cap Cal.45'),
    ('M1911 Customized Cal.45', 'M1911 Customized Cal.45'),
]

RIFLE_MODELS = [
    ('M4 Carbine DSAR-15 5.56mm', 'M4 Carbine DSAR-15 5.56mm'),
    ('M4 14.5" DGIS EMTAN 5.56mm', 'M4 14.5" DGIS EMTAN 5.56mm'),
    ('M16A1 Rifle 5.56mm', 'M16A1 Rifle 5.56mm'),
    ('M14 Rifle 7.62mm', 'M14 Rifle 7.62mm'),
    ('M653 Carbine 5.56mm', 'M653 Carbine 5.56mm'),
]

ALL_WEAPON_MODELS = PISTOL_MODELS + RIFLE_MODELS

# ---------------------------------------------------------------------------
# AMMUNITION TYPES — synced with inventory/models.py PISTOL/RIFLE_AMMUNITION_TYPES
# Actual military designations used throughout Pistol/Rifle/Transaction models.
# ---------------------------------------------------------------------------
PISTOL_AMMUNITION_TYPES = [
    ('Cal.45 Ball 433 Ctg', 'Cal.45 Ball 433 Ctg'),
    ('M882 9x19mm Ball 435 Ctg', 'M882 9x19mm Ball 435 Ctg'),
]

RIFLE_AMMUNITION_TYPES = [
    ('M193 5.56mm Ball 428 Ctg', 'M193 5.56mm Ball 428 Ctg'),
    ('M855 5.56mm Ball 429 Ctg', 'M855 5.56mm Ball 429 Ctg'),
    ('M80 7.62x51mm Ball 431 Ctg', 'M80 7.62x51mm Ball 431 Ctg'),
]

# Combined — used where weapon type is not yet determined
AMMUNITION_TYPES = PISTOL_AMMUNITION_TYPES + RIFLE_AMMUNITION_TYPES

# ---------------------------------------------------------------------------
# AMMUNITION LOADS — doctrinal round counts per duty type
# Basic Load  : 360 rounds (M16A1, M653, M4 carbines)
# Security Load: 210 rounds
# ---------------------------------------------------------------------------
AMMUNITION_LOADS = [
    ('Basic Load', 'Basic Load'),        # 360 rounds — M16A1 / M653 / M4 Carbine
    ('Security Load', 'Security Load'),  # 210 rounds
]

AMMUNITION_LOAD_ROUNDS = {
    'Basic Load': 360,
    'Security Load': 210,
}

# ---------------------------------------------------------------------------
# MAGAZINE TYPES — synced with inventory/models.py ALL_MAGAZINE_TYPES
# ---------------------------------------------------------------------------
PISTOL_MAGAZINE_TYPES = [
    ('Mag Assy, 9mm: Glock 17', 'Mag Assy, 9mm: Glock 17'),
    ('Mag Assy, Cal.45: 7 rds Cap', 'Mag Assy, Cal.45: 7 rds Cap'),
    ('Mag Assy, Cal.45: 8 rds Cap', 'Mag Assy, Cal.45: 8 rds Cap'),
    ('Mag Assy, Cal.45: Hi Cap', 'Mag Assy, Cal.45: Hi Cap'),
]

RIFLE_MAGAZINE_TYPES = [
    ('Mag Assy, 5.56mm: 20 rds Cap Alloy', 'Mag Assy, 5.56mm: 20 rds Cap Alloy'),
    ('Mag Assy, 5.56mm: 30 rds Cap Alloy', 'Mag Assy, 5.56mm: 30 rds Cap Alloy'),
    ('Mag Assy, 5.56mm: EMTAN', 'Mag Assy, 5.56mm: EMTAN'),
    ('Mag Assy, 7.62mm: M14', 'Mag Assy, 7.62mm: M14'),
]

ALL_MAGAZINE_TYPES = PISTOL_MAGAZINE_TYPES + RIFLE_MAGAZINE_TYPES

# ---------------------------------------------------------------------------
# ACCESSORIES — synced with inventory/models.py ACCESSORY_TYPES
# ---------------------------------------------------------------------------
ACCESSORY_TYPES = [
    ('Pistol Holster', 'Pistol Holster'),
    ('Pistol Magazine Pouch', 'Pistol Magazine Pouch'),
    ('Rifle Sling', 'Rifle Sling'),
    ('Bandoleer', 'Bandoleer'),
]

# Max accessory units per withdrawal — synced with inventory/models.py ACCESSORY_MAX_QTY
ACCESSORY_MAX_QTY = {
    'Pistol Holster': 1,
    'Pistol Magazine Pouch': 3,
    'Rifle Sling': 1,
    'Bandoleer': 1,
}

# Max magazines per weapon type per withdrawal — synced with inventory/models.py MAGAZINE_MAX_QTY
MAGAZINE_MAX_QTY = {
    'Pistol': 4,    # 4 magazines per pistol per AMMO_ASSIGNMENT spec
    'Rifle': None,  # No hard cap defined (Short/Long issued as needed)
}

# ---------------------------------------------------------------------------
# AMMO–WEAPON COMPATIBILITY — synced with inventory/models.py AMMO_WEAPON_COMPATIBILITY
# ---------------------------------------------------------------------------
AMMO_WEAPON_COMPATIBILITY = {
    'Cal.45 Ball 433 Ctg': [
        'M1911 Cal.45',
        'Armscor Hi Cap Cal.45',
        'RIA Hi Cap Cal.45',
        'M1911 Customized Cal.45',
    ],
    'M882 9x19mm Ball 435 Ctg': [
        'Glock 17 9mm',
    ],
    'M193 5.56mm Ball 428 Ctg': [
        'M4 Carbine DSAR-15 5.56mm',
        'M4 14.5" DGIS EMTAN 5.56mm',
        'M16A1 Rifle 5.56mm',
        'M653 Carbine 5.56mm',
    ],
    'M855 5.56mm Ball 429 Ctg': [
        'M4 Carbine DSAR-15 5.56mm',
        'M4 14.5" DGIS EMTAN 5.56mm',
        'M16A1 Rifle 5.56mm',
        'M653 Carbine 5.56mm',
    ],
    'M80 7.62x51mm Ball 431 Ctg': [
        'M14 Rifle 7.62mm',
    ],
}

# ---------------------------------------------------------------------------
# ITEM STATUS & CONDITION — synced with inventory/models.py STATUS_CHOICES / CONDITION_CHOICES
# ---------------------------------------------------------------------------
STATUS_CHOICES = [
    ('Issued', 'Issued'),
    ('Available', 'Available'),
    ('Under Maintenance', 'Under Maintenance'),
    ('For Turn In', 'For Turn In'),
    ('Turned In', 'Turned In'),
    ('Decommissioned', 'Decommissioned'),
]

CONDITION_CHOICES = [
    ('Serviceable', 'Serviceable'),
    ('Unserviceable', 'Unserviceable'),
    ('Lost', 'Lost'),
    ('Tampered', 'Tampered'),
]

# ---------------------------------------------------------------------------
# WEAPON TYPE — used to distinguish pistol pools from rifle pools (magazines, ammo)
# ---------------------------------------------------------------------------
WEAPON_TYPE_CHOICES = [
    ('Pistol', 'Pistol'),
    ('Rifle', 'Rifle'),
]

# ---------------------------------------------------------------------------
# Inventory_Analytics model
# Tracks aggregate counts (total / issued / available) per item pool.
# - item_type  : broad category (Small Arms, Ammunition, Magazines, Accessories)
# - weapon_type: Pistol or Rifle (used for magazine/ammo pools; blank for accessories)
# - category   : sub-type within item_type (weapon model, ammo designation, etc.)
# - total_count, issued_count, available_count: quantity snapshot
# - last_updated: auto-set on every save for freshness tracking
# ---------------------------------------------------------------------------
class Inventory_Analytics(models.Model):
    item_type = models.CharField(
        max_length=50,
        choices=ITEMS_CHOICES,
        help_text="Broad item category."
    )
    weapon_type = models.CharField(
        max_length=10,
        choices=WEAPON_TYPE_CHOICES,
        blank=True,
        null=True,
        help_text="Pistol or Rifle — used for magazines and ammunition pools."
    )
    category = models.CharField(
        max_length=100,
        help_text="Sub-type: weapon model, ammo designation, magazine type, or accessory type."
    )
    total_count = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Total number of items registered."
    )
    issued_count = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Number currently issued to personnel."
    )
    available_count = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Number currently available. Should equal total_count - issued_count."
    )
    par_count = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Number of withdrawal transactions issued under PAR (Property Acknowledgement Receipt)."
    )
    tr_count = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Number of withdrawal transactions issued under TR (Temporary Receipt)."
    )
    last_updated = models.DateTimeField(
        default=timezone.now,
        help_text="Timestamp of last analytics snapshot update."
    )

    class Meta:
        verbose_name = "Inventory Analytics"
        verbose_name_plural = "Inventory Analytics"
        ordering = ['item_type', 'weapon_type', 'category']

    def __str__(self):
        weapon = f" ({self.weapon_type})" if self.weapon_type else ""
        return f"{self.item_type}{weapon} — {self.category}"

    def sync_available(self):
        """Recomputes available_count as total_count - issued_count and saves."""
        self.available_count = max(self.total_count - self.issued_count, 0)
        self.last_updated = timezone.now()
        self.save(update_fields=['available_count', 'last_updated'])

    @classmethod
    def sync_from_inventory(cls, date_from=None, duty_type=None, log_status=None):
        """
        Rebuilds all Inventory_Analytics rows from live inventory data.
        Called automatically when the admin changelist is opened.

        Args:
            date_from (datetime, optional): When set, ALL counts are derived from
                Transactions with timestamp >= date_from (Today / This Week / This Month).
                issued_count    = withdrawals in the period.
                available_count = returns in the period.
                total_count     = withdrawals + returns in the period.
                When None, the current inventory state is used for total/issued/available.
            duty_type (str, optional): When set, only Transactions with this duty_type
                are counted (e.g. 'Duty Sentinel', 'Duty Security').
            log_status (str, optional): When set, only Transactions that belong to a
                TransactionLog with this status are counted
                (e.g. 'Open', 'Partially Returned', 'Closed').

        Coverage:
          - Small Arms (Pistol): grouped by model.
          - Small Arms (Rifle) : grouped by model.
          - Magazines           : grouped by weapon_type + type — sums pool quantity.
          - Ammunition          : grouped by type — sums pool quantity.
          - Accessories         : grouped by type — sums pool quantity.
        """
        from django.db.models import Count, Q, Sum
        from .models import Pistol, Rifle, Magazine, Ammunition, Accessory
        from armguard.apps.transactions.models import Transaction, TransactionLogs

        # REC-04: No longer delete all rows first — the upsert at the bottom handles
        # create-or-update in-place, and stale rows are pruned at the end.
        rows = []
        now = timezone.now()

        # Base withdrawal queryset
        txn_qs = Transaction.objects.filter(transaction_type='Withdrawal')
        # -- Date filter
        if date_from:
            txn_qs = txn_qs.filter(timestamp__gte=date_from)
        # -- Duty type filter (now uses 'purpose' field)
        if duty_type:
            txn_qs = txn_qs.filter(purpose=duty_type)
        # -- Log status filter: collect transaction IDs from TransactionLogs rows
        #    that carry the requested status, then narrow txn_qs to those IDs.
        if log_status:
            log_txn_fk_fields = [
                'withdrawal_pistol_transaction_id',
                'withdrawal_rifle_transaction_id',
                'withdrawal_pistol_magazine_transaction_id',
                'withdrawal_rifle_magazine_transaction_id',
                'withdrawal_pistol_ammunition_transaction_id',
                'withdrawal_rifle_ammunition_transaction_id',
                'withdrawal_pistol_holster_transaction_id',
                'withdrawal_magazine_pouch_transaction_id',
            ]
            logs_qs = TransactionLogs.objects.filter(log_status=log_status)
            matched_ids: set = set()
            for fk in log_txn_fk_fields:
                matched_ids.update(
                    logs_qs.exclude(**{f'{fk}__isnull': True})
                            .values_list(fk, flat=True)
                )
            txn_qs = txn_qs.filter(pk__in=matched_ids)

        # ── Pre-compute PAR / TR counts from Withdrawal transactions ───────────
        # Small Arms — Pistol (group by pistol model)
        pistol_par = {
            e['pistol__model']: e['n']
            for e in txn_qs.filter(
                pistol__isnull=False,
                issuance_type__startswith='PAR'
            ).values('pistol__model').annotate(n=Count('pk'))
        }
        pistol_tr = {
            e['pistol__model']: e['n']
            for e in txn_qs.filter(
                pistol__isnull=False,
                issuance_type__startswith='TR'
            ).values('pistol__model').annotate(n=Count('pk'))
        }
        # Small Arms — Rifle (group by rifle model)
        rifle_par = {
            e['rifle__model']: e['n']
            for e in txn_qs.filter(
                rifle__isnull=False,
                issuance_type__startswith='PAR'
            ).values('rifle__model').annotate(n=Count('pk'))
        }
        rifle_tr = {
            e['rifle__model']: e['n']
            for e in txn_qs.filter(
                rifle__isnull=False,
                issuance_type__startswith='TR'
            ).values('rifle__model').annotate(n=Count('pk'))
        }
        # Magazines — combine pistol_magazine + rifle_magazine transactions
        # Key: "<type> (<weapon_type>)"
        mag_par: dict = {}
        mag_tr: dict = {}
        for fk_field in ('pistol_magazine', 'rifle_magazine'):
            for e in txn_qs.filter(
                issuance_type__startswith='PAR',
                **{f'{fk_field}__isnull': False}
            ).values(f'{fk_field}__type', f'{fk_field}__weapon_type').annotate(n=Count('pk')):
                key = f"{e[f'{fk_field}__type']} ({e[f'{fk_field}__weapon_type']})"
                mag_par[key] = mag_par.get(key, 0) + e['n']
            for e in txn_qs.filter(
                issuance_type__startswith='TR',
                **{f'{fk_field}__isnull': False}
            ).values(f'{fk_field}__type', f'{fk_field}__weapon_type').annotate(n=Count('pk')):
                key = f"{e[f'{fk_field}__type']} ({e[f'{fk_field}__weapon_type']})"
                mag_tr[key] = mag_tr.get(key, 0) + e['n']
        # Ammunition — combine pistol_ammunition + rifle_ammunition transactions
        ammo_par: dict = {}
        ammo_tr: dict = {}
        for fk_field in ('pistol_ammunition', 'rifle_ammunition'):
            for e in txn_qs.filter(
                issuance_type__startswith='PAR',
                **{f'{fk_field}__isnull': False}
            ).values(f'{fk_field}__type').annotate(n=Count('pk')):
                t = e[f'{fk_field}__type']
                ammo_par[t] = ammo_par.get(t, 0) + e['n']
            for e in txn_qs.filter(
                issuance_type__startswith='TR',
                **{f'{fk_field}__isnull': False}
            ).values(f'{fk_field}__type').annotate(n=Count('pk')):
                t = e[f'{fk_field}__type']
                ammo_tr[t] = ammo_tr.get(t, 0) + e['n']
        # Accessories — accessories are stored as quantity-only integer fields on
        # TransactionLogs (no FK), so filter by qty > 0 and use fixed type names.
        _ACC_QTY_MAP = [
            ('pistol_holster_quantity',  'Pistol Holster'),
            ('magazine_pouch_quantity',  'Pistol Magazine Pouch'),
            ('rifle_sling_quantity',     'Rifle Sling'),
            ('bandoleer_quantity',       'Bandoleer'),
        ]
        acc_par: dict = {}
        acc_tr: dict = {}
        for qty_field, typename in _ACC_QTY_MAP:
            n_par = txn_qs.filter(
                issuance_type__startswith='PAR',
                **{f'{qty_field}__gt': 0}
            ).count()
            if n_par:
                acc_par[typename] = acc_par.get(typename, 0) + n_par
            n_tr = txn_qs.filter(
                issuance_type__startswith='TR',
                **{f'{qty_field}__gt': 0}
            ).count()
            if n_tr:
                acc_tr[typename] = acc_tr.get(typename, 0) + n_tr

        # ── Build item-type rows ───────────────────────────────────────────────
        # When date_from is set every column is derived from transactions in that
        # period:  issued_count = withdrawals, available_count = returns,
        # total_count = withdrawals + returns.
        # When no date filter the current inventory state is used (original behaviour).
        if date_from:
            return_qs = Transaction.objects.filter(
                transaction_type='Return', timestamp__gte=date_from
            )

            # --- Small Arms: Pistol ---
            pistol_issued = {
                e['pistol__model']: e['n']
                for e in txn_qs.filter(pistol__isnull=False)
                .values('pistol__model').annotate(n=Count('pk'))
            }
            pistol_returned = {
                e['pistol__model']: e['n']
                for e in return_qs.filter(pistol__isnull=False)
                .values('pistol__model').annotate(n=Count('pk'))
            }
            for model in sorted(set(list(pistol_issued) + list(pistol_returned))):
                iss = pistol_issued.get(model, 0)
                ret = pistol_returned.get(model, 0)
                rows.append(cls(
                    item_type='Small Arms', weapon_type='Pistol', category=model,
                    total_count=iss + ret, issued_count=iss, available_count=ret,
                    par_count=pistol_par.get(model, 0),
                    tr_count=pistol_tr.get(model, 0),
                    last_updated=now,
                ))

            # --- Small Arms: Rifle ---
            rifle_issued = {
                e['rifle__model']: e['n']
                for e in txn_qs.filter(rifle__isnull=False)
                .values('rifle__model').annotate(n=Count('pk'))
            }
            rifle_returned = {
                e['rifle__model']: e['n']
                for e in return_qs.filter(rifle__isnull=False)
                .values('rifle__model').annotate(n=Count('pk'))
            }
            for model in sorted(set(list(rifle_issued) + list(rifle_returned))):
                iss = rifle_issued.get(model, 0)
                ret = rifle_returned.get(model, 0)
                rows.append(cls(
                    item_type='Small Arms', weapon_type='Rifle', category=model,
                    total_count=iss + ret, issued_count=iss, available_count=ret,
                    par_count=rifle_par.get(model, 0),
                    tr_count=rifle_tr.get(model, 0),
                    last_updated=now,
                ))

            # --- Magazines ---
            mag_issued: dict = {}
            mag_returned: dict = {}
            for fk, qty in [('pistol_magazine', 'pistol_magazine_quantity'),
                             ('rifle_magazine',  'rifle_magazine_quantity')]:
                for e in txn_qs.filter(**{f'{fk}__isnull': False}).values(
                    f'{fk}__type', f'{fk}__weapon_type'
                ).annotate(s=Sum(qty)):
                    key = f"{e[f'{fk}__type']} ({e[f'{fk}__weapon_type']})"
                    mag_issued[key] = mag_issued.get(key, 0) + (e['s'] or 0)
                for e in return_qs.filter(**{f'{fk}__isnull': False}).values(
                    f'{fk}__type', f'{fk}__weapon_type'
                ).annotate(s=Sum(qty)):
                    key = f"{e[f'{fk}__type']} ({e[f'{fk}__weapon_type']})"
                    mag_returned[key] = mag_returned.get(key, 0) + (e['s'] or 0)
            for key in sorted(set(list(mag_issued) + list(mag_returned))):
                wtype = key.split('(')[-1].rstrip(')').strip() if '(' in key else None
                iss = mag_issued.get(key, 0)
                ret = mag_returned.get(key, 0)
                rows.append(cls(
                    item_type='Magazines', weapon_type=wtype, category=key,
                    total_count=iss + ret, issued_count=iss, available_count=ret,
                    par_count=mag_par.get(key, 0),
                    tr_count=mag_tr.get(key, 0),
                    last_updated=now,
                ))

            # --- Ammunition ---
            ammo_issued: dict = {}
            ammo_returned: dict = {}
            for fk, qty in [('pistol_ammunition', 'pistol_ammunition_quantity'),
                             ('rifle_ammunition',  'rifle_ammunition_quantity')]:
                for e in txn_qs.filter(**{f'{fk}__isnull': False}).values(
                    f'{fk}__type'
                ).annotate(s=Sum(qty)):
                    t = e[f'{fk}__type']
                    ammo_issued[t] = ammo_issued.get(t, 0) + (e['s'] or 0)
                for e in return_qs.filter(**{f'{fk}__isnull': False}).values(
                    f'{fk}__type'
                ).annotate(s=Sum(qty)):
                    t = e[f'{fk}__type']
                    ammo_returned[t] = ammo_returned.get(t, 0) + (e['s'] or 0)
            for t in sorted(set(list(ammo_issued) + list(ammo_returned))):
                iss = ammo_issued.get(t, 0)
                ret = ammo_returned.get(t, 0)
                rows.append(cls(
                    item_type='Ammunition', weapon_type=None, category=t,
                    total_count=iss + ret, issued_count=iss, available_count=ret,
                    par_count=ammo_par.get(t, 0),
                    tr_count=ammo_tr.get(t, 0),
                    last_updated=now,
                ))

            # --- Accessories ---
            acc_issued_q: dict = {}
            acc_returned_q: dict = {}
            for qty_field, typename in _ACC_QTY_MAP:
                s_iss = txn_qs.filter(**{f'{qty_field}__gt': 0}).aggregate(
                    s=Sum(qty_field)
                )['s'] or 0
                if s_iss:
                    acc_issued_q[typename] = acc_issued_q.get(typename, 0) + s_iss
                s_ret = return_qs.filter(**{f'{qty_field}__gt': 0}).aggregate(
                    s=Sum(qty_field)
                )['s'] or 0
                if s_ret:
                    acc_returned_q[typename] = acc_returned_q.get(typename, 0) + s_ret
            for t in sorted(set(list(acc_issued_q) + list(acc_returned_q))):
                iss = acc_issued_q.get(t, 0)
                ret = acc_returned_q.get(t, 0)
                rows.append(cls(
                    item_type='Accessories', weapon_type=None, category=t,
                    total_count=iss + ret, issued_count=iss, available_count=ret,
                    par_count=acc_par.get(t, 0),
                    tr_count=acc_tr.get(t, 0),
                    last_updated=now,
                ))

        else:
            # No date filter — reflect current inventory state.

            # ── Small Arms: Pistol ──────────────────────────────────────────────
            for entry in Pistol.objects.values('model').annotate(
                total=Count('pk'),
                issued=Count('pk', filter=Q(item_status='Issued')),
                available=Count('pk', filter=Q(item_status='Available')),
            ):
                rows.append(cls(
                    item_type='Small Arms',
                    weapon_type='Pistol',
                    category=entry['model'],
                    total_count=entry['total'],
                    issued_count=entry['issued'],
                    available_count=entry['available'],
                    par_count=pistol_par.get(entry['model'], 0),
                    tr_count=pistol_tr.get(entry['model'], 0),
                    last_updated=now,
                ))

            # ── Small Arms: Rifle ───────────────────────────────────────────────
            for entry in Rifle.objects.values('model').annotate(
                total=Count('pk'),
                issued=Count('pk', filter=Q(item_status='Issued')),
                available=Count('pk', filter=Q(item_status='Available')),
            ):
                rows.append(cls(
                    item_type='Small Arms',
                    weapon_type='Rifle',
                    category=entry['model'],
                    total_count=entry['total'],
                    issued_count=entry['issued'],
                    available_count=entry['available'],
                    par_count=rifle_par.get(entry['model'], 0),
                    tr_count=rifle_tr.get(entry['model'], 0),
                    last_updated=now,
                ))

            # ── Magazines ──────────────────────────────────────────────────────
            for entry in Magazine.objects.values('weapon_type', 'type').annotate(
                qty=Sum('quantity'),
            ):
                label = f"{entry['type']} ({entry['weapon_type']})"
                rows.append(cls(
                    item_type='Magazines',
                    weapon_type=entry['weapon_type'],
                    category=label,
                    total_count=entry['qty'] or 0,
                    issued_count=0,
                    available_count=entry['qty'] or 0,
                    par_count=mag_par.get(label, 0),
                    tr_count=mag_tr.get(label, 0),
                    last_updated=now,
                ))

            # ── Ammunition ─────────────────────────────────────────────────────
            for entry in Ammunition.objects.values('type').annotate(
                qty=Sum('quantity'),
            ):
                rows.append(cls(
                    item_type='Ammunition',
                    weapon_type=None,
                    category=entry['type'],
                    total_count=entry['qty'] or 0,
                    issued_count=0,
                    available_count=entry['qty'] or 0,
                    par_count=ammo_par.get(entry['type'], 0),
                    tr_count=ammo_tr.get(entry['type'], 0),
                    last_updated=now,
                ))

            # ── Accessories ────────────────────────────────────────────────────
            for entry in Accessory.objects.values('type').annotate(
                qty=Sum('quantity'),
            ):
                rows.append(cls(
                    item_type='Accessories',
                    weapon_type=None,
                    category=entry['type'],
                    total_count=entry['qty'] or 0,
                    issued_count=0,
                    available_count=entry['qty'] or 0,
                    par_count=acc_par.get(entry['type'], 0),
                    tr_count=acc_tr.get(entry['type'], 0),
                    last_updated=now,
                ))

        # REC-04: Deduplicate any leftover duplicate rows that may exist from the
        # old DELETE+bulk_create approach. For each (item_type, weapon_type, category)
        # group keep only the row with the highest pk; delete the extras so that the
        # update_or_create below never hits MultipleObjectsReturned.
        from django.db.models import Max
        for dup in (
            cls.objects.values('item_type', 'weapon_type', 'category')
            .annotate(max_pk=Max('pk'), cnt=models.Count('pk'))
            .filter(cnt__gt=1)
        ):
            cls.objects.filter(
                item_type=dup['item_type'],
                weapon_type=dup['weapon_type'],
                category=dup['category'],
            ).exclude(pk=dup['max_pk']).delete()

        # REC-04: Upsert each row keyed on (item_type, weapon_type, category) so existing
        # rows are updated in-place rather than demolished and recreated on every admin page
        # load. Stale rows (items removed from inventory) are pruned at the end.
        seen_keys = set()
        for row in rows:
            key = (row.item_type, row.weapon_type, row.category)
            seen_keys.add(key)
            cls.objects.update_or_create(
                item_type=row.item_type,
                weapon_type=row.weapon_type,
                category=row.category,
                defaults={
                    'total_count':     row.total_count,
                    'issued_count':    row.issued_count,
                    'available_count': row.available_count,
                    'par_count':       row.par_count,
                    'tr_count':        row.tr_count,
                    'last_updated':    row.last_updated,
                }
            )
        # Prune stale rows (items removed from inventory since the last rebuild).
        for stale in cls.objects.all():
            if (stale.item_type, stale.weapon_type, stale.category) not in seen_keys:
                stale.delete()


# ---------------------------------------------------------------------------
# AnalyticsSnapshot
# Stores a dated copy of every Inventory_Analytics row so that counts can be
# compared across days.  Rows are written by the `snapshot_analytics` management
# command (run daily via Windows Task Scheduler) and are never auto-wiped.
# ---------------------------------------------------------------------------
class AnalyticsSnapshot(models.Model):
    snapshot_date = models.DateField(
        help_text="Calendar date this snapshot was taken."
    )
    item_type = models.CharField(max_length=50, choices=ITEMS_CHOICES)
    weapon_type = models.CharField(
        max_length=10, choices=WEAPON_TYPE_CHOICES, blank=True, null=True
    )
    category = models.CharField(max_length=100)
    total_count = models.PositiveIntegerField(default=0)
    issued_count = models.PositiveIntegerField(default=0)
    available_count = models.PositiveIntegerField(default=0)
    par_count = models.PositiveIntegerField(default=0)
    tr_count = models.PositiveIntegerField(default=0)
    taken_at = models.DateTimeField(
        default=timezone.now,
        help_text="Exact timestamp when this snapshot row was saved."
    )

    class Meta:
        verbose_name = "Analytics Snapshot"
        verbose_name_plural = "Analytics Snapshots"
        ordering = ['-snapshot_date', 'item_type', 'weapon_type', 'category']

    def __str__(self):
        weapon = f" ({self.weapon_type})" if self.weapon_type else ""
        return f"[{self.snapshot_date}] {self.item_type}{weapon} — {self.category}"

    @classmethod
    def take_snapshot(cls):
        """
        Reads all current Inventory_Analytics rows and saves them as today's
        snapshot.  If a snapshot for today already exists it is overwritten
        (delete + re-insert) so running the command twice on the same day is safe.
        """
        from django.utils import timezone as tz
        today = tz.localdate()
        # Sync live analytics first so the snapshot reflects the latest state
        Inventory_Analytics.sync_from_inventory()
        live_rows = Inventory_Analytics.objects.all()
        # Remove any existing rows for today before inserting fresh ones
        cls.objects.filter(snapshot_date=today).delete()
        now = tz.now()
        snapshot_rows = [
            cls(
                snapshot_date=today,
                item_type=row.item_type,
                weapon_type=row.weapon_type,
                category=row.category,
                total_count=row.total_count,
                issued_count=row.issued_count,
                available_count=row.available_count,
                par_count=row.par_count,
                tr_count=row.tr_count,
                taken_at=now,
            )
            for row in live_rows
        ]
        cls.objects.bulk_create(snapshot_rows)
        return len(snapshot_rows)

