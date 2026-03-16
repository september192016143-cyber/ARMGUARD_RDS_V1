import os
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.http import FileResponse, Http404
from django.conf import settings


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


def _build_magazine_table():
    from armguard.apps.inventory.models import Magazine
    from armguard.apps.transactions.models import TransactionLogs
    from django.db.models import Sum
    from django.urls import reverse

    open_statuses = ('Open', 'Partially Returned')
    on_stock_map = {
        row['type']: row['total']
        for row in Magazine.objects.values('type').annotate(total=Sum('quantity'))
    }
    pistol_agg = TransactionLogs.objects.filter(
        log_status__in=open_statuses,
        withdraw_pistol_magazine_quantity__isnull=False,
    ).aggregate(w=Sum('withdraw_pistol_magazine_quantity'), r=Sum('return_pistol_magazine_quantity'))
    rifle_agg = TransactionLogs.objects.filter(
        log_status__in=open_statuses,
        withdraw_rifle_magazine_quantity__isnull=False,
    ).aggregate(w=Sum('withdraw_rifle_magazine_quantity'), r=Sum('return_rifle_magazine_quantity'))
    pistol_issued = max((pistol_agg['w'] or 0) - (pistol_agg['r'] or 0), 0)
    rifle_issued  = max((rifle_agg['w']  or 0) - (rifle_agg['r']  or 0), 0)

    pistol_par_agg = TransactionLogs.objects.filter(
        log_status__in=open_statuses,
        issuance_type='PAR (Property Acknowledgement Receipt)',
        withdraw_pistol_magazine_quantity__isnull=False,
    ).aggregate(w=Sum('withdraw_pistol_magazine_quantity'), r=Sum('return_pistol_magazine_quantity'))
    rifle_par_agg = TransactionLogs.objects.filter(
        log_status__in=open_statuses,
        issuance_type='PAR (Property Acknowledgement Receipt)',
        withdraw_rifle_magazine_quantity__isnull=False,
    ).aggregate(w=Sum('withdraw_rifle_magazine_quantity'), r=Sum('return_rifle_magazine_quantity'))
    pistol_tr_agg = TransactionLogs.objects.filter(
        log_status__in=open_statuses,
        issuance_type='TR (Temporary Receipt)',
        withdraw_pistol_magazine_quantity__isnull=False,
    ).aggregate(w=Sum('withdraw_pistol_magazine_quantity'), r=Sum('return_pistol_magazine_quantity'))
    rifle_tr_agg = TransactionLogs.objects.filter(
        log_status__in=open_statuses,
        issuance_type='TR (Temporary Receipt)',
        withdraw_rifle_magazine_quantity__isnull=False,
    ).aggregate(w=Sum('withdraw_rifle_magazine_quantity'), r=Sum('return_rifle_magazine_quantity'))

    pistol_issued_par = max((pistol_par_agg['w'] or 0) - (pistol_par_agg['r'] or 0), 0)
    rifle_issued_par  = max((rifle_par_agg['w']  or 0) - (rifle_par_agg['r']  or 0), 0)
    pistol_issued_tr  = max((pistol_tr_agg['w']  or 0) - (pistol_tr_agg['r']  or 0), 0)
    rifle_issued_tr   = max((rifle_tr_agg['w']   or 0) - (rifle_tr_agg['r']   or 0), 0)

    MAG_DEFS = [
        ('Pistol Standard', 'Pistol', 'Pistol Magazine',               pistol_issued, pistol_issued_par, pistol_issued_tr),
        ('Short',           'Rifle',  'Rifle Magazine (Short/20-rnd)', rifle_issued,  rifle_issued_par,  rifle_issued_tr),
        ('Long',            'Rifle',  'Rifle Magazine (Long/30-rnd)',  rifle_issued,  rifle_issued_par,  rifle_issued_tr),
    ]
    list_url = reverse('magazine-list')
    rows, totals = [], {'on_stock': 0, 'issued': 0, 'issued_par': 0, 'issued_tr': 0}
    for type_key, label, nomenclature, issued, issued_par, issued_tr in MAG_DEFS:
        on_stock = on_stock_map.get(type_key, 0)
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
    on_stock_map = {
        row['type']: row['total']
        for row in Accessory.objects.values('type').annotate(total=Sum('quantity'))
    }
    agg = TransactionLogs.objects.filter(log_status__in=open_statuses).aggregate(
        holster_w=Sum('withdraw_pistol_holster_quantity'),
        holster_r=Sum('return_pistol_holster_quantity'),
        pouch_w=Sum('withdraw_magazine_pouch_quantity'),
        pouch_r=Sum('return_magazine_pouch_quantity'),
        sling_w=Sum('withdraw_rifle_sling_quantity'),
        sling_r=Sum('return_rifle_sling_quantity'),
        band_w=Sum('withdraw_bandoleer_quantity'),
        band_r=Sum('return_bandoleer_quantity'),
    )
    # PAR / TR split per accessory type
    par_agg = TransactionLogs.objects.filter(
        log_status__in=open_statuses,
        issuance_type='PAR (Property Acknowledgement Receipt)',
    ).aggregate(
        holster_w=Sum('withdraw_pistol_holster_quantity'),
        holster_r=Sum('return_pistol_holster_quantity'),
        pouch_w=Sum('withdraw_magazine_pouch_quantity'),
        pouch_r=Sum('return_magazine_pouch_quantity'),
        sling_w=Sum('withdraw_rifle_sling_quantity'),
        sling_r=Sum('return_rifle_sling_quantity'),
        band_w=Sum('withdraw_bandoleer_quantity'),
        band_r=Sum('return_bandoleer_quantity'),
    )
    tr_agg = TransactionLogs.objects.filter(
        log_status__in=open_statuses,
        issuance_type='TR (Temporary Receipt)',
    ).aggregate(
        holster_w=Sum('withdraw_pistol_holster_quantity'),
        holster_r=Sum('return_pistol_holster_quantity'),
        pouch_w=Sum('withdraw_magazine_pouch_quantity'),
        pouch_r=Sum('return_magazine_pouch_quantity'),
        sling_w=Sum('withdraw_rifle_sling_quantity'),
        sling_r=Sum('return_rifle_sling_quantity'),
        band_w=Sum('withdraw_bandoleer_quantity'),
        band_r=Sum('return_bandoleer_quantity'),
    )

    ACC_DEFS = [
        ('Pistol Holster',        'Pistol', 'Pistol Holster',        'holster_w', 'holster_r'),
        ('Pistol Magazine Pouch', 'Pistol', 'Pistol Magazine Pouch', 'pouch_w',   'pouch_r'),
        ('Rifle Sling',           'Rifle',  'Rifle Sling',           'sling_w',   'sling_r'),
        ('Bandoleer',             'Rifle',  'Bandoleer',             'band_w',    'band_r'),
    ]
    list_url = reverse('accessory-list')
    rows, totals = [], {'on_stock': 0, 'issued': 0, 'issued_par': 0, 'issued_tr': 0}
    for type_key, label, nomenclature, w_key, r_key in ACC_DEFS:
        on_stock   = on_stock_map.get(type_key, 0)
        issued     = max((agg[w_key] or 0) - (agg[r_key] or 0), 0)
        issued_par = max((par_agg[w_key] or 0) - (par_agg[r_key] or 0), 0)
        issued_tr  = max((tr_agg[w_key]  or 0) - (tr_agg[r_key]  or 0), 0)
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
    from armguard.apps.personnel.models import Personnel
    from armguard.apps.inventory.models import Pistol, Rifle, Magazine, Ammunition, Accessory
    from armguard.apps.transactions.models import Transaction

    today = timezone.localdate()
    cache_key = f'dashboard_stats_{today}'

    stats = cache.get(cache_key)
    if stats is None:
        from armguard.apps.transactions.models import TransactionLogs

        withdrawals_today = Transaction.objects.filter(
            transaction_type='Withdrawal', timestamp__date=today
        ).count()
        returns_today = Transaction.objects.filter(
            transaction_type='Return', timestamp__date=today
        ).count()

        _officer_ranks = {'2LT', '1LT', 'CPT', 'MAJ', 'LTCOL', 'COL',
                          'BGEN', 'MGEN', 'LTGEN', 'GEN'}

        # Count firearms that are *currently* outstanding (not yet returned).
        # Each TransactionLog row may track a pistol, a rifle, or both; count
        # each weapon independently so a combined pistol+rifle log adds 2.
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
            'short_magazine_available': Magazine.objects.filter(type='Short').aggregate(t=Sum('quantity'))['t'] or 0,
            'long_magazine_available':  Magazine.objects.filter(type='Long').aggregate(t=Sum('quantity'))['t'] or 0,
            'short_magazine_issued':   (lambda a: max((a['w'] or 0) - (a['r'] or 0), 0))(
                TransactionLogs.objects.filter(log_status__in=_open, withdraw_rifle_magazine__type='Short')
                .aggregate(w=Sum('withdraw_rifle_magazine_quantity'), r=Sum('return_rifle_magazine_quantity'))
            ),
            'long_magazine_issued':    (lambda a: max((a['w'] or 0) - (a['r'] or 0), 0))(
                TransactionLogs.objects.filter(log_status__in=_open, withdraw_rifle_magazine__type='Long')
                .aggregate(w=Sum('withdraw_rifle_magazine_quantity'), r=Sum('return_rifle_magazine_quantity'))
            ),
            'total_ammo_qty':         Ammunition.objects.aggregate(t=Sum('quantity'))['t'] or 0,
            'total_transactions':     Transaction.objects.count(),
            'total_transactions_today': withdrawals_today + returns_today,
            'withdrawals_today':      withdrawals_today,
            'returns_today':          returns_today,
            'issued_TR':              issued_tr,
            'issued_PAR':             issued_par,
            'total_issued':           issued_tr + issued_par,
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


@login_required
def download_ssl_cert(request):
    """Serve the self-signed SSL certificate as a download.

    Windows users can open the downloaded .crt file and click
    "Install Certificate → Local Machine → Trusted Root Certification Authorities"
    to eliminate the browser "Not secure" warning on the LAN.

    Windows users can open the downloaded .crt file and click
    "Install Certificate → Local Machine → Trusted Root Certification Authorities"
    to eliminate the browser "Not secure" warning on the LAN.
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


@login_required
def ssl_cert_status(request):
    """Return the current SSL cert mtime so the frontend can compare against its
    localStorage ack. The ack is stored client-side so it persists across logins.
    Response: {"cert_mtime": float}  (0.0 when no cert file exists)
    """
    from django.http import JsonResponse
    cert_path = settings.SSL_CERT_PATH
    if not os.path.isfile(cert_path):
        return JsonResponse({'cert_mtime': 0.0})
    return JsonResponse({'cert_mtime': os.path.getmtime(cert_path)})


@login_required
def dashboard_cards_json(request):
    """Return live counts for all four stat cards — no cache — for real-time polling."""
    from django.http import JsonResponse
    from armguard.apps.personnel.models import Personnel
    from armguard.apps.inventory.models import Magazine
    from armguard.apps.transactions.models import Transaction, TransactionLogs
    from django.db.models import Sum

    today = timezone.localdate()

    _officer_ranks = {'2LT', '1LT', 'CPT', 'MAJ', 'LTCOL', 'COL',
                      'BGEN', 'MGEN', 'LTGEN', 'GEN'}

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

    withdrawals_today = Transaction.objects.filter(
        transaction_type='Withdrawal', timestamp__date=today).count()
    returns_today = Transaction.objects.filter(
        transaction_type='Return', timestamp__date=today).count()

    return JsonResponse({
        # Personnel card
        'total_personnel':          Personnel.objects.filter(status='Active').count(),
        'officers_count':           Personnel.objects.filter(status='Active', rank__in=list(_officer_ranks)).count(),
        'enlisted_count':           Personnel.objects.filter(status='Active').exclude(rank__in=list(_officer_ranks)).count(),
        # Magazine card
        'total_magazine_qty':       Magazine.objects.aggregate(t=Sum('quantity'))['t'] or 0,
        'short_magazine_available': Magazine.objects.filter(type='Short').aggregate(t=Sum('quantity'))['t'] or 0,
        'long_magazine_available':  Magazine.objects.filter(type='Long').aggregate(t=Sum('quantity'))['t'] or 0,
        'short_magazine_issued': (lambda a: max((a['w'] or 0) - (a['r'] or 0), 0))(
            TransactionLogs.objects.filter(log_status__in=_open, withdraw_rifle_magazine__type='Short')
            .aggregate(w=Sum('withdraw_rifle_magazine_quantity'), r=Sum('return_rifle_magazine_quantity'))
        ),
        'long_magazine_issued': (lambda a: max((a['w'] or 0) - (a['r'] or 0), 0))(
            TransactionLogs.objects.filter(log_status__in=_open, withdraw_rifle_magazine__type='Long')
            .aggregate(w=Sum('withdraw_rifle_magazine_quantity'), r=Sum('return_rifle_magazine_quantity'))
        ),
        # Issued Firearms card
        'issued_TR':                issued_tr,
        'issued_PAR':               issued_par,
        'total_issued':             issued_tr + issued_par,
        # Transactions Today card
        'total_transactions_today': withdrawals_today + returns_today,
        'withdrawals_today':        withdrawals_today,
        'returns_today':            returns_today,
    })


@login_required
def dashboard_tables_json(request):
    """Return live analytics table data for all four tables — used by real-time poller."""
    from django.http import JsonResponse

    inventory_rows, inventory_totals = _build_inventory_table()
    ammo_rows,      ammo_totals      = _build_ammo_table()
    magazine_rows,  magazine_totals  = _build_magazine_table()
    accessory_rows, accessory_totals = _build_accessory_table()

    def _row_fields(row, keys):
        return {k: row.get(k, 0) for k in keys}

    return JsonResponse({
        'inventory': {
            'rows': [
                _row_fields(r, ['nomenclature', 'possessed', 'on_stock',
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
                _row_fields(r, ['nomenclature', 'basic_load', 'training', 'issued',
                                'unserviceable', 'expenditures', 'on_hand', 'lost'])
                for r in ammo_rows
            ],
            'totals': _row_fields(ammo_totals,
                                  ['basic_load', 'training', 'issued',
                                   'unserviceable', 'expenditures', 'on_hand', 'lost']),
        },
        'magazine': {
            'rows': [
                _row_fields(r, ['nomenclature', 'on_stock', 'issued_par', 'issued_tr'])
                for r in magazine_rows
            ],
            'totals': _row_fields(magazine_totals, ['on_stock', 'issued_par', 'issued_tr']),
        },
        'accessory': {
            'rows': [
                _row_fields(r, ['nomenclature', 'on_stock', 'issued_par', 'issued_tr'])
                for r in accessory_rows
            ],
            'totals': _row_fields(accessory_totals, ['on_stock', 'issued_par', 'issued_tr']),
        },
    })


@login_required
def issued_stats_json(request):
    """Return live issued TR/PAR counts — no cache — for real-time polling."""
    from django.http import JsonResponse
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
