from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Sum, Count, Q
from django.utils import timezone


# ── Nomenclature & ordering constants (mirrors RDS core/views.py) ──────────
_NOMENCLATURE = {
    'Glock 17 9mm':              'Pistol, 9mm: Glock 17',
    'M1911 Cal.45':              'Pistol, Cal.45: M1911',
    'Armscor Hi Cap Cal.45':     'Pistol, Cal.45: Hi Cap (Armscor)',
    'RIA Hi Cap Cal.45':         'Pistol, Cal.45: Hi Cap (RIA)',
    'M1911 Customized Cal.45':   'Pistol, Cal.45: M1911 (Customized)',
    'M4 Carbine DSAR-15 5.56mm': 'Carbine, 5.56mm: M4 (DSAR-15)',
    'M4 14.5" DGIS EMTAN 5.56mm':'Carbine, 5.56mm: M4 14.5" (EMTAN)',
    'M16A1 Rifle 5.56mm':        'Rifle, 5.56mm: M16A1',
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

    _zero = {k: 0 for k in _AGG_FIELDS}
    data = {}
    for model_name in _MODEL_ORDER:
        nom = _NOMENCLATURE.get(model_name, '')
        if 'Pistol' in nom or 'pistol' in model_name.lower():
            url_name, item_type = 'pistol-list', 'pistol'
            agg = pistol_data.get(model_name, {**_zero, 'model': model_name})
        else:
            url_name, item_type = 'rifle-list', 'rifle'
            agg = rifle_data.get(model_name, {**_zero, 'model': model_name})

        data[model_name] = dict(
            nomenclature=nom,
            item_type=item_type,
            model=model_name,
            list_url=reverse(url_name) + f'?q={quote(model_name)}',
            **{k: agg.get(k, 0) for k in _AGG_FIELDS},
        )

    rows = [data[m] for m in _MODEL_ORDER]

    def _sum(col):
        return sum(r[col] for r in rows)

    totals = {k: _sum(k) for k in ('possessed', 'on_stock', 'issued',
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
                  'return_pistol_ammunition_quantity')

    # Single query for all open rifle-ammo log quantities
    rifle_logs = TransactionLogs.objects.filter(
        withdraw_rifle_ammunition__type__in=[t for t in _AMMO_ORDER if t not in _PISTOL_AMMO_TYPES],
        log_status__in=open_statuses,
    ).values_list('withdraw_rifle_ammunition__type',
                  'withdraw_rifle_ammunition_quantity',
                  'return_rifle_ammunition_quantity')

    # Accumulate issued qty per ammo type
    issued_map: dict[str, int] = {}
    for ammo_type, w, r in list(pistol_logs) + list(rifle_logs):
        if ammo_type:
            issued_map[ammo_type] = issued_map.get(ammo_type, 0) + max((w or 0) - (r or 0), 0)

    rows = []
    totals = {k: 0 for k in ('basic_load', 'training', 'issued',
                              'unserviceable', 'expenditures', 'on_hand', 'lost')}
    list_url = reverse('ammunition-list')

    for ammo_type in _AMMO_ORDER:
        on_hand = on_hand_map.get(ammo_type, 0)
        issued  = issued_map.get(ammo_type, 0)
        row = dict(
            nomenclature=_AMMO_NOMENCLATURE.get(ammo_type, ammo_type),
            ammo_type=ammo_type,
            basic_load=on_hand + issued,
            training=0,
            issued=issued,
            unserviceable=0,
            expenditures=0,
            on_hand=on_hand,
            lost=0,
            list_url=list_url,
        )
        rows.append(row)
        for k in totals:
            totals[k] += row[k]

    return rows, totals


@login_required
def dashboard_view(request):
    from armguard.apps.personnel.models import Personnel
    from armguard.apps.inventory.models import Pistol, Rifle, Magazine, Ammunition, Accessory
    from armguard.apps.transactions.models import Transaction

    today = timezone.localdate()
    cache_key = f'dashboard_stats_{today}'

    stats = cache.get(cache_key)
    if stats is None:
        withdrawals_today = Transaction.objects.filter(
            transaction_type='Withdrawal', timestamp__date=today
        ).count()
        returns_today = Transaction.objects.filter(
            transaction_type='Return', timestamp__date=today
        ).count()

        _officer_ranks = {'2LT', '1LT', 'CPT', 'MAJ', 'LTCOL', 'COL',
                          'BGEN', 'MGEN', 'LTGEN', 'GEN'}

        stats = {
            'total_personnel':        Personnel.objects.filter(status='Active').count(),
            'inactive_personnel':     Personnel.objects.filter(status='Inactive').count(),
            'officers_count':         Personnel.objects.filter(status='Active', rank__in=_officer_ranks).count(),
            'enlisted_count':         Personnel.objects.filter(status='Active').exclude(rank__in=_officer_ranks).count(),
            'total_pistols':          Pistol.objects.count(),
            'pistols_available':      Pistol.objects.filter(item_status='Available').count(),
            'pistols_issued':         Pistol.objects.filter(item_status='Issued').count(),
            'total_rifles':           Rifle.objects.count(),
            'rifles_available':       Rifle.objects.filter(item_status='Available').count(),
            'rifles_issued':          Rifle.objects.filter(item_status='Issued').count(),
            'total_magazine_qty':     Magazine.objects.aggregate(t=Sum('quantity'))['t'] or 0,
            'total_ammo_qty':         Ammunition.objects.aggregate(t=Sum('quantity'))['t'] or 0,
            'total_transactions':     Transaction.objects.count(),
            'total_transactions_today': withdrawals_today + returns_today,
            'withdrawals_today':      withdrawals_today,
            'returns_today':          returns_today,
        }
        cache.set(cache_key, stats, 60)

    context = dict(stats)
    context['inventory_rows'], context['inventory_totals'] = _build_inventory_table()
    context['ammo_rows'], context['ammo_totals'] = _build_ammo_table()

    return render(request, 'dashboard/dashboard.html', context)
