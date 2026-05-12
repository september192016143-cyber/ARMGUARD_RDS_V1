import os
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.http import FileResponse, Http404, JsonResponse
from django.conf import settings
from armguard.utils.permissions import can_view_inventory as _can_view_inv


# ── Nomenclature & ordering constants (mirrors RDS core/views.py) ──────────
_NOMENCLATURE = {
    'Glock 17 9mm':              'Pistol, 9mm: Glock 17',
    'M1911 Cal.45':              'Pistol, Cal.45: M1911',
    'Armscor Hi Cap Cal.45':     'Pistol, Cal.45: Hi Cap (Armscor)',
    'RIA Hi Cap Cal.45':         'Pistol, Cal.45: Hi Cap (RIA)',
    'M1911 Customized Cal.45':   'Pistol, Cal.45: M1911 (Customized)',
    'M4 Carbine DSAR-15 5.56mm': 'Carbine, 5.56mm: M4 (DSAR-15)',
    'M4 14.5" DGIS EMTAN 5.56mm':'Carbine, 5.56mm: M4 14.5" (EMTAN)',
    'M16A1 Rifle 5.56mm':        'Rifle, 5.56mm: M16',
    'M14 Rifle 7.62mm':          'Rifle, 7.62mm: M14',
    'M653 Carbine 5.56mm':       'Carbine, 5.56mm: M653',
}

_MODEL_ORDER = [
    'M4 Carbine DSAR-15 5.56mm',
    'M4 14.5" DGIS EMTAN 5.56mm',
    'M653 Carbine 5.56mm',
    'Glock 17 9mm',
    'Armscor Hi Cap Cal.45',
    'RIA Hi Cap Cal.45',
    'M1911 Cal.45',
    'M1911 Customized Cal.45',
    'M16A1 Rifle 5.56mm',
    'M14 Rifle 7.62mm',
]

_AMMO_NOMENCLATURE = {
    'M193 5.56mm Ball 428 Ctg':   '(428) Ctg, 5.56mm: Ball, M193',
    'M855 5.56mm Ball 429 Ctg':   '(429) Ctg, 5.56mm: Ball, M855',
    'M80 7.62x51mm Ball 431 Ctg': '(431) Ctg, 7.62x51mm: Ball, M80',
    'M882 9x19mm Ball 435 Ctg':   '(435) Ctg, 9x19mm: Ball, M882',
    'Cal.45 Ball 433 Ctg':        '(433) Ctg, Cal.45: Ball',
}

_AMMO_ORDER = [
    'M193 5.56mm Ball 428 Ctg',
    'M855 5.56mm Ball 429 Ctg',
    'M80 7.62x51mm Ball 431 Ctg',
    'M882 9x19mm Ball 435 Ctg',
    'Cal.45 Ball 433 Ctg',
]

_PISTOL_AMMO_TYPES = {'Cal.45 Ball 433 Ctg', 'M882 9x19mm Ball 435 Ctg'}


def _build_inventory_table():
    # 5.6 FIX: Replace 10 per-model queries with 2 grouped aggregate queries
    # (one for Pistol, one for Rifle), then merge into the display order.
    from armguard.apps.inventory.models import Pistol, Rifle
    from armguard.apps.transactions.models import Transaction as _Txn
    from django.db.models import Subquery, OuterRef
    from django.urls import reverse
    from urllib.parse import quote

    _AGG_FIELDS = dict(
        possessed     = Count('item_id'),
        on_stock      = Count('item_id', filter=Q(item_status__in=(
                            'Available', 'Under Maintenance', 'For Turn In'))),
        issued        = Count('item_id', filter=Q(item_status='Issued')),
        serviceable   = Count('item_id', filter=Q(item_condition='Serviceable')),
        unserviceable = Count('item_id', filter=Q(item_condition='Unserviceable')),
        lost          = Count('item_id', filter=Q(item_condition='Lost')),
        tampered      = Count('item_id', filter=Q(item_condition='Tampered')),
    )

    pistol_data = {
        row['model']: row
        for row in Pistol.objects.values('model').annotate(**_AGG_FIELDS)
    }
    rifle_data = {
        row['model']: row
        for row in Rifle.objects.values('model').annotate(**_AGG_FIELDS)
    }

    # PAR / TR split — annotate each issued item with its latest withdrawal
    # issuance_type, then group in Python (avoids Subquery-inside-Count
    # which is unreliable across Django/SQLite versions).
    from collections import defaultdict
    _pistol_issuance = (
        _Txn.objects
        .filter(transaction_type='Withdrawal', pistol=OuterRef('pk'))
        .order_by('-timestamp')
        .values('issuance_type')[:1]
    )
    _rifle_issuance = (
        _Txn.objects
        .filter(transaction_type='Withdrawal', rifle=OuterRef('pk'))
        .order_by('-timestamp')
        .values('issuance_type')[:1]
    )

    _pistol_par_tr = defaultdict(lambda: {'issued_par': 0, 'issued_tr': 0})
    for model, issuance in (
        Pistol.objects
        .annotate(last_issuance=Subquery(_pistol_issuance))
        .filter(item_status='Issued')
        .values_list('model', 'last_issuance')
    ):
        t = issuance or ''
        if t.startswith('PAR'):
            _pistol_par_tr[model]['issued_par'] += 1
        elif t.startswith('TR'):
            _pistol_par_tr[model]['issued_tr'] += 1

    _rifle_par_tr = defaultdict(lambda: {'issued_par': 0, 'issued_tr': 0})
    for model, issuance in (
        Rifle.objects
        .annotate(last_issuance=Subquery(_rifle_issuance))
        .filter(item_status='Issued')
        .values_list('model', 'last_issuance')
    ):
        t = issuance or ''
        if t.startswith('PAR'):
            _rifle_par_tr[model]['issued_par'] += 1
        elif t.startswith('TR'):
            _rifle_par_tr[model]['issued_tr'] += 1

    _zero = {k: 0 for k in _AGG_FIELDS}
    data = {}
    for model_name in _MODEL_ORDER:
        nom = _NOMENCLATURE.get(model_name, '')
        if 'Pistol' in nom or 'pistol' in model_name.lower():
            url_name, item_type = 'pistol-list', 'pistol'
            agg     = pistol_data.get(model_name, {**_zero, 'model': model_name})
            par_tr  = _pistol_par_tr[model_name]
        else:
            url_name, item_type = 'rifle-list', 'rifle'
            agg     = rifle_data.get(model_name, {**_zero, 'model': model_name})
            par_tr  = _rifle_par_tr[model_name]

        data[model_name] = dict(
            nomenclature=nom,
            item_type=item_type,
            model=model_name,
            list_url=reverse(url_name) + f'?q={quote(model_name)}',
            **{k: agg.get(k, 0) for k in _AGG_FIELDS},
            issued_par=par_tr.get('issued_par', 0),
            issued_tr =par_tr.get('issued_tr',  0),
        )

    rows = [data[m] for m in _MODEL_ORDER]

    def _sum(col):
        return sum(r[col] for r in rows)

    totals = {k: _sum(k) for k in ('possessed', 'on_stock', 'issued',
                                    'issued_par', 'issued_tr',
                                    'serviceable', 'unserviceable', 'lost', 'tampered')}
    return rows, totals


def _build_ammo_table():
    # 5.6 FIX: Replace 5*2 per-type queries with 1 aggregated Ammunition query and
    # 2 bulk TransactionLogs queries (one for pistol ammo, one for rifle ammo).
    from armguard.apps.inventory.models import Ammunition
    from armguard.apps.transactions.models import TransactionLogs
    from django.db.models import Sum
    from django.urls import reverse

    open_statuses = ('Open', 'Partially Returned')

    # Single query: on-hand qty grouped by ammo type
    on_hand_map = {
        row['type']: row['total']
        for row in Ammunition.objects.values('type').annotate(total=Sum('quantity'))
    }

    # Single query for all open pistol-ammo log quantities
    pistol_logs = TransactionLogs.objects.filter(
        withdraw_pistol_ammunition__type__in=_PISTOL_AMMO_TYPES,
        log_status__in=open_statuses,
    ).values_list('withdraw_pistol_ammunition__type',
                  'withdraw_pistol_ammunition_quantity',
                  'return_pistol_ammunition_quantity',
                  'issuance_type')

    # Single query for all open rifle-ammo log quantities
    rifle_logs = TransactionLogs.objects.filter(
        withdraw_rifle_ammunition__type__in=[t for t in _AMMO_ORDER if t not in _PISTOL_AMMO_TYPES],
        log_status__in=open_statuses,
    ).values_list('withdraw_rifle_ammunition__type',
                  'withdraw_rifle_ammunition_quantity',
                  'return_rifle_ammunition_quantity',
                  'issuance_type')

    # Accumulate issued qty per ammo type (total, PAR, TR)
    issued_map: dict[str, int] = {}
    issued_par_map: dict[str, int] = {}
    issued_tr_map: dict[str, int] = {}
    for ammo_type, w, r, itype in list(pistol_logs) + list(rifle_logs):
        if ammo_type:
            net = max((w or 0) - (r or 0), 0)
            issued_map[ammo_type] = issued_map.get(ammo_type, 0) + net
            if itype and 'PAR' in itype:
                issued_par_map[ammo_type] = issued_par_map.get(ammo_type, 0) + net
            elif itype and 'TR' in itype:
                issued_tr_map[ammo_type] = issued_tr_map.get(ammo_type, 0) + net

    rows = []
    totals = {k: 0 for k in ('basic_load', 'issued', 'issued_par', 'issued_tr',
                              'unserviceable', 'serviceable', 'on_hand', 'lost')}
    list_url = reverse('ammunition-list')

    for ammo_type in _AMMO_ORDER:
        on_hand = on_hand_map.get(ammo_type, 0)
        issued  = issued_map.get(ammo_type, 0)
        row = dict(
            nomenclature=_AMMO_NOMENCLATURE.get(ammo_type, ammo_type),
            ammo_type=ammo_type,
            basic_load=on_hand + issued,
            issued=issued,
            issued_par=issued_par_map.get(ammo_type, 0),
            issued_tr=issued_tr_map.get(ammo_type, 0),
            unserviceable=0,
            serviceable=on_hand,
            on_hand=on_hand,
            lost=0,
            list_url=list_url,
        )
        rows.append(row)
        for k in totals:
            totals[k] += row[k]

    return rows, totals


def _build_magazine_table():
    from armguard.apps.inventory.models import Magazine
    from armguard.apps.transactions.models import TransactionLogs
    from django.db.models import Sum
    from django.urls import reverse

    open_statuses = ('Open', 'Partially Returned')
    _PAR = 'PAR (Property Acknowledgement Receipt)'
    _TR  = 'TR (Temporary Receipt)'

    on_stock_map = {}
    for row in Magazine.objects.values('type', 'capacity').annotate(total=Sum('quantity')):
        on_stock_map[row['type']] = on_stock_map.get(row['type'], 0) + row['total']

    def _type_stock(mag_type):
        return on_stock_map.get(mag_type, 0)

    # N+1 FIX: single conditional aggregate per issuance filter covering all 8 types.
    def _mag_agg(qs_filter):
        _PT = 'withdraw_pistol_magazine__type'
        _PC = 'withdraw_rifle_magazine__capacity'
        return TransactionLogs.objects.filter(log_status__in=open_statuses, **qs_filter).aggregate(
            # --- Pistol types (filtered by magazine FK type string) ---
            p9mm_w=Sum('withdraw_pistol_magazine_quantity',
                filter=Q(**{f'{_PT}': 'Mag Assy, 9mm: Glock 17'})),
            p9mm_r=Sum('return_pistol_magazine_quantity',
                filter=Q(return_pistol_magazine__type='Mag Assy, 9mm: Glock 17')),
            p45_7_w=Sum('withdraw_pistol_magazine_quantity',
                filter=Q(**{f'{_PT}': 'Mag Assy, Cal.45: 7 rds Cap'})),
            p45_7_r=Sum('return_pistol_magazine_quantity',
                filter=Q(return_pistol_magazine__type='Mag Assy, Cal.45: 7 rds Cap')),
            p45_8_w=Sum('withdraw_pistol_magazine_quantity',
                filter=Q(**{f'{_PT}': 'Mag Assy, Cal.45: 8 rds Cap'})),
            p45_8_r=Sum('return_pistol_magazine_quantity',
                filter=Q(return_pistol_magazine__type='Mag Assy, Cal.45: 8 rds Cap')),
            p45_hi_w=Sum('withdraw_pistol_magazine_quantity',
                filter=Q(**{f'{_PT}': 'Mag Assy, Cal.45: Hi Cap'})),
            p45_hi_r=Sum('return_pistol_magazine_quantity',
                filter=Q(return_pistol_magazine__type='Mag Assy, Cal.45: Hi Cap')),
            # --- Rifle types (filtered by magazine FK capacity) ---
            short_w=Sum('withdraw_rifle_magazine_quantity',
                filter=Q(**{f'{_PC}': '20-rounds'})),
            short_r=Sum('return_rifle_magazine_quantity',
                filter=Q(return_rifle_magazine__capacity='20-rounds')),
            long_w=Sum('withdraw_rifle_magazine_quantity',
                filter=Q(**{f'{_PC}': '30-rounds'})),
            long_r=Sum('return_rifle_magazine_quantity',
                filter=Q(return_rifle_magazine__capacity='30-rounds')),
            m14_w=Sum('withdraw_rifle_magazine_quantity',
                filter=Q(**{f'{_PC}': 'M14'})),
            m14_r=Sum('return_rifle_magazine_quantity',
                filter=Q(return_rifle_magazine__capacity='M14')),
            emtan_w=Sum('withdraw_rifle_magazine_quantity',
                filter=Q(**{f'{_PC}': 'EMTAN'})),
            emtan_r=Sum('return_rifle_magazine_quantity',
                filter=Q(return_rifle_magazine__capacity='EMTAN')),
        )

    def _net(a, w, r):
        return max((a[w] or 0) - (a[r] or 0), 0)

    total_agg = _mag_agg({})
    par_agg   = _mag_agg({'issuance_type': _PAR})
    tr_agg    = _mag_agg({'issuance_type': _TR})

    MAG_DEFS = [
        ('Pistol-9mm',   'Pistol', 'Mag Assy, 9mm: Glock 17',
            _type_stock('Mag Assy, 9mm: Glock 17'),
            _net(total_agg,'p9mm_w','p9mm_r'), _net(par_agg,'p9mm_w','p9mm_r'), _net(tr_agg,'p9mm_w','p9mm_r')),
        ('Pistol-45-7',  'Pistol', 'Mag Assy, Cal.45: 7 rds Cap',
            _type_stock('Mag Assy, Cal.45: 7 rds Cap'),
            _net(total_agg,'p45_7_w','p45_7_r'), _net(par_agg,'p45_7_w','p45_7_r'), _net(tr_agg,'p45_7_w','p45_7_r')),
        ('Pistol-45-8',  'Pistol', 'Mag Assy, Cal.45: 8 rds Cap',
            _type_stock('Mag Assy, Cal.45: 8 rds Cap'),
            _net(total_agg,'p45_8_w','p45_8_r'), _net(par_agg,'p45_8_w','p45_8_r'), _net(tr_agg,'p45_8_w','p45_8_r')),
        ('Pistol-45-hi', 'Pistol', 'Mag Assy, Cal.45: Hi Cap',
            _type_stock('Mag Assy, Cal.45: Hi Cap'),
            _net(total_agg,'p45_hi_w','p45_hi_r'), _net(par_agg,'p45_hi_w','p45_hi_r'), _net(tr_agg,'p45_hi_w','p45_hi_r')),
        ('Rifle-20',     'Rifle',  'Mag Assy, 5.56mm: 20 rds Cap Alloy',
            _type_stock('Mag Assy, 5.56mm: 20 rds Cap Alloy'),
            _net(total_agg,'short_w','short_r'), _net(par_agg,'short_w','short_r'), _net(tr_agg,'short_w','short_r')),
        ('Rifle-30',     'Rifle',  'Mag Assy, 5.56mm: 30 rds Cap Alloy',
            _type_stock('Mag Assy, 5.56mm: 30 rds Cap Alloy'),
            _net(total_agg,'long_w','long_r'), _net(par_agg,'long_w','long_r'), _net(tr_agg,'long_w','long_r')),
        ('Rifle-M14',    'Rifle',  'Mag Assy, 7.62mm: M14',
            _type_stock('Mag Assy, 7.62mm: M14'),
            _net(total_agg,'m14_w','m14_r'), _net(par_agg,'m14_w','m14_r'), _net(tr_agg,'m14_w','m14_r')),
        ('Rifle-EMTAN',  'Rifle',  'Mag Assy, 5.56mm: EMTAN',
            _type_stock('Mag Assy, 5.56mm: EMTAN'),
            _net(total_agg,'emtan_w','emtan_r'), _net(par_agg,'emtan_w','emtan_r'), _net(tr_agg,'emtan_w','emtan_r')),
    ]
    list_url = reverse('magazine-list')
    rows, totals = [], {'on_stock': 0, 'issued': 0, 'issued_par': 0, 'issued_tr': 0}
    for type_key, label, nomenclature, on_stock, issued, issued_par, issued_tr in MAG_DEFS:
        rows.append(dict(label=label, nomenclature=nomenclature, type=type_key,
                         on_stock=on_stock, issued=issued,
                         issued_par=issued_par, issued_tr=issued_tr,
                         list_url=list_url))
        totals['on_stock']   += on_stock
        totals['issued']     += issued
        totals['issued_par'] += issued_par
        totals['issued_tr']  += issued_tr
    return rows, totals


def _build_accessory_table():
    from armguard.apps.inventory.models import Accessory
    from armguard.apps.transactions.models import TransactionLogs
    from django.db.models import Sum
    from django.urls import reverse

    open_statuses = ('Open', 'Partially Returned')
    _PAR = 'PAR (Property Acknowledgement Receipt)'
    _TR  = 'TR (Temporary Receipt)'

    on_stock_map = {
        row['type']: row['total']
        for row in Accessory.objects.values('type').annotate(total=Sum('quantity'))
    }

    # N+1 FIX: replace 3 separate aggregate queries with 1 conditional aggregate
    # that computes total, PAR, and TR issued quantities in a single DB round-trip.
    _ACC_FIELDS = ('holster', 'pouch', 'sling', 'band')
    _ACC_MAP = {
        'holster': ('withdraw_pistol_holster_quantity',  'return_pistol_holster_quantity'),
        'pouch':   ('withdraw_magazine_pouch_quantity',  'return_magazine_pouch_quantity'),
        'sling':   ('withdraw_rifle_sling_quantity',     'return_rifle_sling_quantity'),
        'band':    ('withdraw_bandoleer_quantity',       'return_bandoleer_quantity'),
    }

    def _build_acc_agg(extra_filter):
        kwargs = {}
        for key, (wf, rf) in _ACC_MAP.items():
            kwargs[f'{key}_w'] = Sum(wf, filter=extra_filter)
            kwargs[f'{key}_r'] = Sum(rf, filter=extra_filter)
        return TransactionLogs.objects.filter(log_status__in=open_statuses).aggregate(**kwargs)

    agg     = _build_acc_agg(Q())
    par_agg = _build_acc_agg(Q(issuance_type=_PAR))
    tr_agg  = _build_acc_agg(Q(issuance_type=_TR))

    def _net(a, key):
        return max((a[f'{key}_w'] or 0) - (a[f'{key}_r'] or 0), 0)

    ACC_DEFS = [
        ('Pistol Holster',        'Pistol', 'Pistol Holster',        'holster'),
        ('Pistol Magazine Pouch', 'Pistol', 'Pistol Magazine Pouch', 'pouch'),
        ('Rifle Sling',           'Rifle',  'Rifle Sling',           'sling'),
        ('Bandoleer',             'Rifle',  'Bandoleer',             'band'),
    ]
    list_url = reverse('accessory-list')
    rows, totals = [], {'on_stock': 0, 'issued': 0, 'issued_par': 0, 'issued_tr': 0}
    for type_key, label, nomenclature, key in ACC_DEFS:
        on_stock   = on_stock_map.get(type_key, 0)
        issued     = _net(agg,     key)
        issued_par = _net(par_agg, key)
        issued_tr  = _net(tr_agg,  key)
        rows.append(dict(label=label, nomenclature=nomenclature, type=type_key,
                         on_stock=on_stock, issued=issued,
                         issued_par=issued_par, issued_tr=issued_tr,
                         list_url=list_url))
        totals['on_stock']   += on_stock
        totals['issued']     += issued
        totals['issued_par'] += issued_par
        totals['issued_tr']  += issued_tr
    return rows, totals


@login_required
def dashboard_view(request):
    if not _can_view_inv(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Forbidden')
    from armguard.apps.personnel.models import Personnel
    from armguard.apps.inventory.models import Pistol, Rifle, Magazine, Ammunition, Accessory
    from armguard.apps.transactions.models import Transaction

    today = timezone.localdate()
    cache_key = f'dashboard_stats_{today}'

    stats = cache.get(cache_key)
    if stats is None:
        from armguard.apps.transactions.models import TransactionLogs

        _officer_ranks = {'2LT', '1LT', 'CPT', 'MAJ', 'LTCOL', 'COL',
                          'BGEN', 'MGEN', 'LTGEN', 'GEN'}
        _open = ('Open', 'Partially Returned')
        _PAR = 'PAR (Property Acknowledgement Receipt)'
        _TR  = 'TR (Temporary Receipt)'

        # N+1 FIX: collapse 17 individual count/aggregate queries into 6
        # conditional aggregates — one per model family.

        # 1 query: personnel counts
        _pers = Personnel.objects.aggregate(
            active=Count('Personnel_ID', filter=Q(status='Active')),
            inactive=Count('Personnel_ID', filter=Q(status='Inactive')),
            officers=Count('Personnel_ID', filter=Q(status='Active', rank__in=_officer_ranks)),
            enlisted=Count('Personnel_ID', filter=Q(status='Active') & ~Q(rank__in=_officer_ranks)),
        )

        # 1 query: pistol counts
        _pistol = Pistol.objects.aggregate(
            total=Count('item_id'),
            available=Count('item_id', filter=Q(item_status='Available')),
            issued=Count('item_id', filter=Q(item_status='Issued')),
        )

        # 1 query: rifle counts
        _rifle = Rifle.objects.aggregate(
            total=Count('item_id'),
            available=Count('item_id', filter=Q(item_status='Available')),
            issued=Count('item_id', filter=Q(item_status='Issued')),
        )

        # 1 query: magazine + ammo totals
        _mag = Magazine.objects.aggregate(
            total=Sum('quantity'),
            short=Sum('quantity', filter=Q(capacity='20-rounds', weapon_type='Rifle')),
            long=Sum('quantity', filter=Q(capacity__in=['30-rounds', 'EMTAN'], weapon_type='Rifle')),
        )

        # 1 query: transaction day totals + all-time count
        _txn = Transaction.objects.aggregate(
            total=Count('transaction_id'),
            withdrawals_today=Count('transaction_id', filter=Q(transaction_type='Withdrawal', timestamp__date=today)),
            returns_today=Count('transaction_id', filter=Q(transaction_type='Return', timestamp__date=today)),
        )

        # 1 query: issued firearm counts + magazine issued counts (open logs only)
        _logs = TransactionLogs.objects.filter(log_status__in=_open).aggregate(
            tr_pistol=Count('record_id', filter=Q(issuance_type=_TR,
                withdraw_pistol__isnull=False, return_pistol__isnull=True)),
            tr_rifle=Count('record_id', filter=Q(issuance_type=_TR,
                withdraw_rifle__isnull=False, return_rifle__isnull=True)),
            par_pistol=Count('record_id', filter=Q(issuance_type=_PAR,
                withdraw_pistol__isnull=False, return_pistol__isnull=True)),
            par_rifle=Count('record_id', filter=Q(issuance_type=_PAR,
                withdraw_rifle__isnull=False, return_rifle__isnull=True)),
            short_mag_w=Sum('withdraw_rifle_magazine_quantity',
                filter=Q(withdraw_rifle_magazine__capacity='20-rounds')),
            short_mag_r=Sum('return_rifle_magazine_quantity',
                filter=Q(withdraw_rifle_magazine__capacity='20-rounds')),
            long_mag_w=Sum('withdraw_rifle_magazine_quantity',
                filter=Q(withdraw_rifle_magazine__capacity__in=['30-rounds', 'EMTAN'])),
            long_mag_r=Sum('return_rifle_magazine_quantity',
                filter=Q(withdraw_rifle_magazine__capacity__in=['30-rounds', 'EMTAN'])),
        )

        issued_tr  = _logs['tr_pistol']  + _logs['tr_rifle']
        issued_par = _logs['par_pistol'] + _logs['par_rifle']

        stats = {
            'total_personnel':          _pers['active']   or 0,
            'inactive_personnel':       _pers['inactive'] or 0,
            'officers_count':           _pers['officers'] or 0,
            'enlisted_count':           _pers['enlisted'] or 0,
            'total_pistols':            _pistol['total']     or 0,
            'pistols_available':        _pistol['available'] or 0,
            'pistols_issued':           _pistol['issued']    or 0,
            'total_rifles':             _rifle['total']     or 0,
            'rifles_available':         _rifle['available'] or 0,
            'rifles_issued':            _rifle['issued']    or 0,
            'total_magazine_qty':       _mag['total'] or 0,
            'short_magazine_available': _mag['short'] or 0,
            'long_magazine_available':  _mag['long']  or 0,
            'short_magazine_issued':    max((_logs['short_mag_w'] or 0) - (_logs['short_mag_r'] or 0), 0),
            'long_magazine_issued':     max((_logs['long_mag_w']  or 0) - (_logs['long_mag_r']  or 0), 0),
            'total_ammo_qty':           Ammunition.objects.aggregate(t=Sum('quantity'))['t'] or 0,
            'total_transactions':       _txn['total']            or 0,
            'total_transactions_today': (_txn['withdrawals_today'] or 0) + (_txn['returns_today'] or 0),
            'withdrawals_today':        _txn['withdrawals_today'] or 0,
            'returns_today':            _txn['returns_today']     or 0,
            'issued_TR':                issued_tr,
            'issued_PAR':               issued_par,
            'total_issued':             issued_tr + issued_par,
        }
        cache.set(cache_key, stats, 60)

    context = dict(stats)

    inv_cache_key = 'dashboard_inventory_tables'
    tables = cache.get(inv_cache_key)
    if tables is None:
        tables = {
            'inventory_rows':    None,
            'inventory_totals':  None,
            'ammo_rows':         None,
            'ammo_totals':       None,
            'magazine_rows':     None,
            'magazine_totals':   None,
            'accessory_rows':    None,
            'accessory_totals':  None,
        }
        tables['inventory_rows'], tables['inventory_totals'] = _build_inventory_table()
        tables['ammo_rows'],      tables['ammo_totals']      = _build_ammo_table()
        tables['magazine_rows'],  tables['magazine_totals']  = _build_magazine_table()
        tables['accessory_rows'], tables['accessory_totals'] = _build_accessory_table()
        cache.set(inv_cache_key, tables, 30)  # 30 s — stays fresh during busy duty shifts

    context.update(tables)

    return render(request, 'dashboard/dashboard.html', context)


def download_ssl_cert(request):
    """Serve the self-signed SSL certificate as a download.
    
    PUBLIC ENDPOINT (no login required) — the certificate is public information
    anyway (transmitted in TLS handshake), so making it easy to download helps
    users install it without fighting the browser's security warning.

    Android: Settings → Security → Install from storage → CA certificate
    Windows: Open .crt file → Install Certificate → Trusted Root CA
    iOS: Download → Settings → Profile Downloaded → Install
    """
    cert_path = settings.SSL_CERT_PATH
    if not os.path.isfile(cert_path):
        raise Http404("SSL certificate file not found on this server.")
    response = FileResponse(
        open(cert_path, 'rb'),
        content_type='application/x-x509-ca-cert',
    )
    response['Content-Disposition'] = 'attachment; filename="armguard-selfsigned.crt"'
    return response


def ssl_cert_status(request):
    """Return the current SSL cert mtime so the frontend can compare against its
    localStorage ack. The ack is stored client-side so it persists across logins.
    Response: {"cert_mtime": float}  (0.0 when no cert file exists)
    
    PUBLIC ENDPOINT — metadata only, no sensitive data.
    """
    from django.http import JsonResponse
    cert_path = settings.SSL_CERT_PATH
    if not os.path.isfile(cert_path):
        return JsonResponse({'cert_mtime': 0.0})
    return JsonResponse({'cert_mtime': os.path.getmtime(cert_path)})


@login_required
def dashboard_cards_json(request):
    """Return live counts for all four stat cards, cached for 10 s.

    10 s matches the JS poll interval in dashboard_cards.js so the DB is hit
    at most ~6 times/minute regardless of how many workers or open tabs exist.
    create_transaction() invalidates 'dashboard_cards_{date}' immediately after
    a new transaction so counts stay accurate within one poll cycle.
    """
    if not _can_view_inv(request.user):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    from armguard.apps.personnel.models import Personnel
    from armguard.apps.inventory.models import Pistol, Rifle, Magazine
    from armguard.apps.transactions.models import Transaction, TransactionLogs
    from django.db.models import Sum

    today = timezone.localdate()
    cards_cache_key = f'dashboard_cards_{today}'
    cached = cache.get(cards_cache_key)
    if cached is not None:
        return JsonResponse(cached)

    _officer_ranks = {'2LT', '1LT', 'CPT', 'MAJ', 'LTCOL', 'COL',
                      'BGEN', 'MGEN', 'LTGEN', 'GEN'}

    _open = ('Open', 'Partially Returned')
    _TR  = 'TR (Temporary Receipt)'
    _PAR = 'PAR (Property Acknowledgement Receipt)'

    _pistol = Pistol.objects.aggregate(
        total=Count('item_id'),
        available=Count('item_id', filter=Q(item_status='Available')),
        issued=Count('item_id', filter=Q(item_status='Issued')),
    )
    _rifle = Rifle.objects.aggregate(
        total=Count('item_id'),
        available=Count('item_id', filter=Q(item_status='Available')),
        issued=Count('item_id', filter=Q(item_status='Issued')),
    )

    _logs = TransactionLogs.objects.filter(log_status__in=_open).aggregate(
        tr_pistol=Count('record_id', filter=Q(issuance_type=_TR,
            withdraw_pistol__isnull=False, return_pistol__isnull=True)),
        tr_rifle=Count('record_id', filter=Q(issuance_type=_TR,
            withdraw_rifle__isnull=False, return_rifle__isnull=True)),
        par_pistol=Count('record_id', filter=Q(issuance_type=_PAR,
            withdraw_pistol__isnull=False, return_pistol__isnull=True)),
        par_rifle=Count('record_id', filter=Q(issuance_type=_PAR,
            withdraw_rifle__isnull=False, return_rifle__isnull=True)),
        short_mag_w=Sum('withdraw_rifle_magazine_quantity',
            filter=Q(withdraw_rifle_magazine__capacity='20-rounds')),
        short_mag_r=Sum('return_rifle_magazine_quantity',
            filter=Q(withdraw_rifle_magazine__capacity='20-rounds')),
        long_mag_w=Sum('withdraw_rifle_magazine_quantity',
            filter=Q(withdraw_rifle_magazine__capacity__in=['30-rounds', 'EMTAN'])),
        long_mag_r=Sum('return_rifle_magazine_quantity',
            filter=Q(withdraw_rifle_magazine__capacity__in=['30-rounds', 'EMTAN'])),
    )

    issued_tr  = _logs['tr_pistol']  + _logs['tr_rifle']
    issued_par = _logs['par_pistol'] + _logs['par_rifle']

    _txn = Transaction.objects.aggregate(
        withdrawals_today=Count('transaction_id', filter=Q(transaction_type='Withdrawal', timestamp__date=today)),
        returns_today=Count('transaction_id', filter=Q(transaction_type='Return', timestamp__date=today)),
    )
    withdrawals_today = _txn['withdrawals_today'] or 0
    returns_today     = _txn['returns_today'] or 0

    data = {
        # Personnel card
        'total_personnel':          Personnel.objects.filter(status='Active').count(),
        'officers_count':           Personnel.objects.filter(status='Active', rank__in=list(_officer_ranks)).count(),
        'enlisted_count':           Personnel.objects.filter(status='Active').exclude(rank__in=list(_officer_ranks)).count(),
        # Firearms card
        'total_pistols':            _pistol['total']     or 0,
        'pistols_available':        _pistol['available'] or 0,
        'pistols_issued':           _pistol['issued']    or 0,
        'total_rifles':             _rifle['total']      or 0,
        'rifles_available':         _rifle['available']  or 0,
        'rifles_issued':            _rifle['issued']     or 0,
        # Magazine card
        'total_magazine_qty':       Magazine.objects.aggregate(t=Sum('quantity'))['t'] or 0,
        'short_magazine_available': Magazine.objects.filter(weapon_type='Rifle', capacity='20-rounds').aggregate(t=Sum('quantity'))['t'] or 0,
        'long_magazine_available':  Magazine.objects.filter(weapon_type='Rifle', capacity__in=['30-rounds', 'EMTAN']).aggregate(t=Sum('quantity'))['t'] or 0,
        'short_magazine_issued':    max((_logs['short_mag_w'] or 0) - (_logs['short_mag_r'] or 0), 0),
        'long_magazine_issued':     max((_logs['long_mag_w']  or 0) - (_logs['long_mag_r']  or 0), 0),
        # Issued Firearms card
        'issued_TR':                issued_tr,
        'issued_PAR':               issued_par,
        'total_issued':             issued_tr + issued_par,
        # Transactions Today card
        'total_transactions_today': withdrawals_today + returns_today,
        'withdrawals_today':        withdrawals_today,
        'returns_today':            returns_today,
    }
    cache.set(cards_cache_key, data, 10)  # 10 s matches the JS poll interval
    return JsonResponse(data)


@login_required
def dashboard_tables_json(request):
    """Return analytics table data — uses the shared 'dashboard_inventory_tables' cache.

    Previously called all four _build_*_table() functions directly with no caching.
    Now reads from the same FileBasedCache key that dashboard_view() writes, so the
    expensive aggregate queries run at most once per 30 s regardless of how many
    workers or open tabs are polling.
    """
    if not _can_view_inv(request.user):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    inv_cache_key = 'dashboard_inventory_tables'
    tables = cache.get(inv_cache_key)
    if tables is None:
        tables = {
            'inventory_rows':   None,
            'inventory_totals': None,
            'ammo_rows':        None,
            'ammo_totals':      None,
            'magazine_rows':    None,
            'magazine_totals':  None,
            'accessory_rows':   None,
            'accessory_totals': None,
        }
        tables['inventory_rows'], tables['inventory_totals'] = _build_inventory_table()
        tables['ammo_rows'],      tables['ammo_totals']      = _build_ammo_table()
        tables['magazine_rows'],  tables['magazine_totals']  = _build_magazine_table()
        tables['accessory_rows'], tables['accessory_totals'] = _build_accessory_table()
        cache.set(inv_cache_key, tables, 30)

    inventory_rows  = tables['inventory_rows']
    inventory_totals = tables['inventory_totals']
    ammo_rows       = tables['ammo_rows']
    ammo_totals     = tables['ammo_totals']
    magazine_rows   = tables['magazine_rows']
    magazine_totals = tables['magazine_totals']
    accessory_rows  = tables['accessory_rows']
    accessory_totals = tables['accessory_totals']

    def _row_fields(row, keys):
        return {k: row.get(k, 0) for k in keys}

    return JsonResponse({
        'inventory': {
            'rows': [
                _row_fields(r, ['nomenclature', 'list_url', 'possessed', 'on_stock',
                                'issued_par', 'issued_tr',
                                'serviceable', 'unserviceable', 'lost', 'tampered'])
                for r in inventory_rows
            ],
            'totals': _row_fields(inventory_totals,
                                  ['possessed', 'on_stock', 'issued_par', 'issued_tr',
                                   'serviceable', 'unserviceable', 'lost', 'tampered']),
        },
        'ammo': {
            'rows': [
                _row_fields(r, ['nomenclature', 'list_url', 'basic_load', 'on_hand', 'issued',
                                'issued_par', 'issued_tr', 'serviceable', 'unserviceable', 'lost'])
                for r in ammo_rows
            ],
            'totals': _row_fields(ammo_totals,
                                  ['basic_load', 'on_hand', 'issued',
                                   'issued_par', 'issued_tr', 'serviceable', 'unserviceable', 'lost']),
        },
        'magazine': {
            'rows': [
                _row_fields(r, ['nomenclature', 'list_url', 'on_stock', 'issued_par', 'issued_tr'])
                for r in magazine_rows
            ],
            'totals': _row_fields(magazine_totals, ['on_stock', 'issued_par', 'issued_tr']),
        },
        'accessory': {
            'rows': [
                _row_fields(r, ['nomenclature', 'list_url', 'on_stock', 'issued_par', 'issued_tr'])
                for r in accessory_rows
            ],
            'totals': _row_fields(accessory_totals, ['on_stock', 'issued_par', 'issued_tr']),
        },
    })


@login_required
def issued_stats_json(request):
    """Return live issued TR/PAR counts — no cache — for real-time polling."""
    if not _can_view_inv(request.user):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    from armguard.apps.transactions.models import TransactionLogs

    _open = ('Open', 'Partially Returned')
    issued_tr = (
        TransactionLogs.objects.filter(
            log_status__in=_open,
            issuance_type='TR (Temporary Receipt)',
            withdraw_pistol__isnull=False, return_pistol__isnull=True,
        ).count()
        + TransactionLogs.objects.filter(
            log_status__in=_open,
            issuance_type='TR (Temporary Receipt)',
            withdraw_rifle__isnull=False, return_rifle__isnull=True,
        ).count()
    )
    issued_par = (
        TransactionLogs.objects.filter(
            log_status__in=_open,
            issuance_type='PAR (Property Acknowledgement Receipt)',
            withdraw_pistol__isnull=False, return_pistol__isnull=True,
        ).count()
        + TransactionLogs.objects.filter(
            log_status__in=_open,
            issuance_type='PAR (Property Acknowledgement Receipt)',
            withdraw_rifle__isnull=False, return_rifle__isnull=True,
        ).count()
    )
    return JsonResponse({
        'issued_TR':    issued_tr,
        'issued_PAR':   issued_par,
        'total_issued': issued_tr + issued_par,
    })
