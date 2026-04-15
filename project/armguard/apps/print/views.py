"""
Print Handler Views - Super Simple
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Count, Q
import os
import re
from django.conf import settings
from utils.pdf_viewer import (
    serve_pdf, serve_pdf_bytes,
    PDF_TYPE_TR, PDF_TYPE_PAR, PDF_TYPE_MO, PDF_TYPE_REPORT,
)
from armguard.apps.transactions.models import Transaction
from armguard.apps.personnel.models import Personnel
from armguard.apps.inventory.models import Pistol, Rifle
from .print_config import QR_SIZE_MM, CARDS_PER_ROW, CARD_WIDTH_MM, CARD_HEIGHT_MM, FONT_SIZE_ID, FONT_SIZE_NAME, FONT_SIZE_BADGE
from .pdf_filler.form_filler import TransactionFormFiller
from django.utils import timezone
from datetime import timedelta
from django.core.paginator import Paginator
# H1 FIX: Import per-module permission helpers.
from armguard.utils.permissions import can_print as _can_print
from armguard.utils.permissions import can_delete_inventory as _can_delete
from armguard.utils.permissions import can_edit_personnel as _can_edit
from armguard.utils.permissions import is_admin as _is_admin


def is_admin_or_armorer(user):
    """Check if user may access the Print module.

    H1 FIX: Delegates to can_print which checks UserProfile.perm_print
    for Administrators, and grants Armorers access by default.
    """
    return _can_print(user)


# ---------------------------------------------------------------------------
# Item Tag Print Manager
# ---------------------------------------------------------------------------

def _item_tag_img_url(request, item_id):
    """Return the URL for an item tag image served through the Django view."""
    from django.urls import reverse
    return reverse('print_handler:serve_item_tag_image', kwargs={'item_id': item_id})


@login_required
def serve_item_tag_image(request, item_id):
    """Serve an item tag PNG file directly through Django."""
    from django.http import FileResponse, Http404, HttpResponseNotModified
    from pathlib import Path
    import time
    if not _can_print(request.user):
        raise Http404('Item not found')
    # Validate item exists in DB before serving any file (prevents path-based enumeration)
    if not Pistol.objects.filter(item_id=item_id).exists() and \
       not Rifle.objects.filter(item_id=item_id).exists():
        raise Http404('Item not found')
    media_root = Path(settings.MEDIA_ROOT).resolve()
    filepath = (media_root / 'item_id_tags' / f"{item_id}.png").resolve()
    # 4.6 FIX: Ensure the resolved path is inside MEDIA_ROOT (prevents path traversal).
    if not str(filepath).startswith(str(media_root)):
        raise Http404('Invalid path')
    if not filepath.exists():
        raise Http404('Item tag image not found')
    # Return 304 if the browser already has a fresh copy (based on file mtime).
    mtime = filepath.stat().st_mtime
    etag = f'"{int(mtime)}"'
    if request.META.get('HTTP_IF_NONE_MATCH') == etag:
        return HttpResponseNotModified()
    response = FileResponse(open(filepath, 'rb'), content_type='image/png')
    response['ETag'] = etag
    response['Cache-Control'] = 'private, max-age=3600'
    return response


@login_required
def print_item_tags(request):
    """
    Item Tag Print Manager — lists all items, shows their tag thumbnail,
    and allows single/bulk printing and re-generation.
    """
    if not _can_print(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('You do not have permission to access the Print module.')
    from armguard.apps.inventory.models import PISTOL_MODELS, RIFLE_MODELS

    search_q     = request.GET.get('q', '').strip()
    type_filter  = request.GET.get('type', '').strip().lower()
    model_filter = request.GET.get('model', '').strip()

    # C7 FIX: Use ORM filtering instead of loading all records into Python memory.
    pistol_qs = Pistol.objects.all()
    rifle_qs  = Rifle.objects.all()

    if search_q:
        pq = (
            Q(serial_number__icontains=search_q) |
            Q(model__icontains=search_q) |
            Q(item_id__icontains=search_q)
        )
        pistol_qs = pistol_qs.filter(pq)
        rifle_qs  = rifle_qs.filter(pq)

    if type_filter == 'pistol':
        rifle_qs = rifle_qs.none()
    elif type_filter == 'rifle':
        pistol_qs = pistol_qs.none()

    if model_filter:
        pistol_qs = pistol_qs.filter(model=model_filter)
        rifle_qs  = rifle_qs.filter(model=model_filter)

    # Merge and sort; both querysets are now DB-filtered before loading into memory.
    all_items = sorted(
        list(pistol_qs) + list(rifle_qs),
        key=lambda i: (i.item_type, i.model, i.item_number or '')
    )

    # PERF: one os.listdir() to build a membership set instead of N os.path.exists() calls
    tag_dir = os.path.join(settings.MEDIA_ROOT, 'item_id_tags')
    existing_tags = set(os.listdir(tag_dir)) if os.path.isdir(tag_dir) else set()

    item_tags = []
    for item in all_items:
        has_tag = f"{item.item_id}.png" in existing_tags
        thumb_url = _item_tag_img_url(request, item.item_id) if has_tag else None
        item_tags.append({
            'item': item,
            'has_tag': has_tag,
            'thumb_url': thumb_url,
        })

    total      = len(item_tags)
    with_tag   = sum(1 for t in item_tags if t['has_tag'])

    context = {
        'item_tags':           item_tags,
        'search_q':            search_q,
        'type_filter':         type_filter,
        'model_filter':        model_filter,
        'pistol_model_choices': PISTOL_MODELS,
        'rifle_model_choices':  RIFLE_MODELS,
        'total':               total,
        'with_tag':            with_tag,
        'without_tag':         total - with_tag,
        'is_admin':            _can_delete(request.user),
        'can_print':           _can_print(request.user),
    }
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'print/print_item_tags_grid.html', context)
    return render(request, 'print/print_item_tags.html', context)


@login_required
@require_POST
def generate_item_tags(request):
    """
    Bulk-generate item tag PNGs.
    force=1 → regenerate ALL (even those that exist).
    Returns JSON {generated, skipped, errors}
    """
    if not _can_print(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    from utils.item_tag_generator import generate_item_tag

    force     = request.POST.get('force', '0') == '1'
    generated = 0
    skipped   = 0
    errors    = []

    # PERF: one os.listdir() instead of N os.path.exists() calls when not forcing
    if not force:
        tag_dir_gi = os.path.join(settings.MEDIA_ROOT, 'item_id_tags')
        existing_tag_files = set(os.listdir(tag_dir_gi)) if os.path.isdir(tag_dir_gi) else set()
    else:
        existing_tag_files = set()

    for item in list(Pistol.objects.all()) + list(Rifle.objects.all()):
        if not force and f"{item.item_id}.png" in existing_tag_files:
            skipped += 1
            continue
        try:
            generate_item_tag(item)
            generated += 1
        except Exception as exc:
            errors.append({'id': item.item_id, 'serial': item.serial_number, 'error': str(exc)})

    return JsonResponse({'success': True, 'generated': generated, 'skipped': skipped, 'errors': errors})


@login_required
@require_POST
def regenerate_item_tag(request, item_id):
    """Regenerate the tag PNG for a single item (AJAX POST)."""
    if not _can_print(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    try:
        item = Pistol.objects.get(item_id=item_id)
    except Pistol.DoesNotExist:
        try:
            item = Rifle.objects.get(item_id=item_id)
        except Rifle.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Item not found'}, status=404)
    try:
        from utils.item_tag_generator import generate_item_tag
        generate_item_tag(item)
        thumb_url = _item_tag_img_url(request, item_id)
        return JsonResponse({'success': True, 'thumb_url': thumb_url})
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
@require_POST
def delete_item_tag(request, item_id):
    """Delete the tag PNG for a single item from disk (admin only, AJAX POST)."""
    if not _can_delete(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    from pathlib import Path
    media_root = Path(settings.MEDIA_ROOT).resolve()
    filepath = (media_root / 'item_id_tags' / f"{item_id}.png").resolve()
    # 4.6 FIX: Prevent path traversal — reject any path that escapes MEDIA_ROOT.
    if not str(filepath).startswith(str(media_root)):
        return JsonResponse({'success': False, 'error': 'Invalid item ID'}, status=400)
    deleted = False
    if filepath.exists():
        try:
            filepath.unlink()
            deleted = True
        except Exception as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=500)

    # Clear the item_tag ImageField on the model if it points to this file
    try:
        item = None
        try:
            item = Pistol.objects.get(item_id=item_id)
        except Pistol.DoesNotExist:
            item = Rifle.objects.get(item_id=item_id)
        if item and item.item_tag:
            # Remove the DB reference; Django storage will attempt to delete the
            # physical file (already gone via os.remove above, so this is a no-op
            # on disk but clears the DB field correctly).
            item.item_tag.delete(save=True)
    except Exception:
        pass  # Non-fatal

    if deleted:
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Tag file not found'}, status=404)


@login_required
def print_item_tags_view(request):
    """Print-ready page for selected (or all) item tags."""
    ids_param = request.GET.get('ids', '')
    show_all  = request.GET.get('all', '')

    if show_all:
        items_qs = sorted(
            list(Pistol.objects.all()) + list(Rifle.objects.all()),
            key=lambda i: (i.item_type, i.model, i.item_number or '')
        )
    elif ids_param:
        id_list = [i.strip() for i in ids_param.split(',') if i.strip()]
        pistols  = list(Pistol.objects.filter(item_id__in=id_list))
        rifles   = list(Rifle.objects.filter(item_id__in=id_list))
        items_qs = sorted(
            pistols + rifles,
            key=lambda i: (i.item_type, i.model, i.item_number or '')
        )
    else:
        items_qs = []

    try:
        stack = min(max(int(request.GET.get('stack', 1)), 1), 3)
    except (ValueError, TypeError):
        stack = 1

    from utils.item_tag_generator import get_stacked_tag_b64

    # PERF: one os.listdir() instead of N os.path.exists() calls
    tag_dir = os.path.join(settings.MEDIA_ROOT, 'item_id_tags')
    existing_tags = set(os.listdir(tag_dir)) if os.path.isdir(tag_dir) else set()

    tags = []
    for item in items_qs:
        if f"{item.item_id}.png" not in existing_tags:
            continue
        if stack == 1:
            tag_src = _item_tag_img_url(request, item.item_id)
        else:
            tag_src = get_stacked_tag_b64(item, stack)
        tags.append({'item': item, 'tag_url': tag_src, 'stack': stack})

    return render(request, 'print/print_item_tags_printview.html', {'tags': tags, 'stack': stack})


@login_required
def print_transaction_form(request, transaction_id=None):
    """Print transaction form (HTML preview — no PDF)."""
    transaction = None
    if transaction_id:
        transaction = get_object_or_404(Transaction, transaction_id=transaction_id)

    context = {
        'transaction': transaction,
    }
    return render(request, 'print/print_transaction_form.html', context)


@login_required
def reprint_tr(request):
    """Searchable list of TR transactions for reprinting"""
    if not _can_print(request.user):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('dashboard')
    q           = (request.GET.get('q') or '').strip()
    txn_type    = (request.GET.get('txn_type') or '').strip()
    range_filter = (request.GET.get('range') or '').strip().lower()
    date_from   = (request.GET.get('date_from') or '').strip()
    date_to     = (request.GET.get('date_to') or '').strip()

    transactions = (
        Transaction.objects
        .filter(issuance_type__startswith='TR')
        .select_related('personnel', 'pistol', 'rifle')
        .order_by('-timestamp')
    )

    if q:
        transactions = transactions.filter(
            Q(personnel__last_name__icontains=q) |
            Q(personnel__first_name__icontains=q) |
            Q(personnel__AFSN__icontains=q) |
            Q(personnel__Personnel_ID__icontains=q) |
            Q(transaction_id__icontains=q)
        )

    # TRs are only issued for Withdrawals — Returns are always excluded
    transactions = transactions.filter(transaction_type='Withdrawal')

    if date_from:
        try:
            from datetime import datetime
            transactions = transactions.filter(timestamp__date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
        except ValueError:
            pass
    if date_to:
        try:
            from datetime import datetime
            transactions = transactions.filter(timestamp__date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass

    if not date_from and not date_to:
        range_days = {'day': 1, 'week': 7, 'month': 30}
        if range_filter in range_days:
            since = timezone.now() - timedelta(days=range_days[range_filter])
            transactions = transactions.filter(timestamp__gte=since)

    total = transactions.count()
    paginator = Paginator(transactions, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'transactions':   page_obj,
        'page_obj':       page_obj,
        'q':              q,
        'selected_type':  txn_type,
        'selected_range': range_filter,
        'date_from':      date_from,
        'date_to':        date_to,
        'total':          total,
    }
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'print/reprint_tr_rows.html', context)
    return render(request, 'print/reprint_tr.html', context)


def _firearms_evaluation():
    """Return per-nomenclature count data for the Daily Firearms Evaluation report.

    Columns:
    - STOCK        : items physically in the armory (Available / Under Maintenance / For Turn In)
    - PAR          : items currently issued via PAR (Property Acknowledgement Receipt)
    - TR           : items currently issued via TR (Temporary Receipt)
    - UNSERVICEABLE: items with condition = Unserviceable (counted across all statuses)
    - TOTAL        : STOCK + PAR + TR
    """
    from django.db.models import Subquery, OuterRef
    from armguard.apps.transactions.models import Transaction as _Txn

    # Subquery: issuance_type of the most recent Withdrawal for each Pistol/Rifle
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

    pistols = Pistol.objects.annotate(last_issuance=Subquery(_pistol_issuance))
    rifles  = Rifle.objects.annotate(last_issuance=Subquery(_rifle_issuance))

    NOMENCLATURES = [
        {'label': 'PISTOL,9MM GLOCK 17',     'qs': pistols, 'models': ['Glock 17 9mm']},
        {'label': 'PISTOL CAL.45: M1911',     'qs': pistols, 'models': ['M1911 Cal.45', 'M1911 Customized Cal.45']},
        {'label': 'PISTOL CAL.45: (HI-CAP)', 'qs': pistols, 'models': ['Armscor Hi Cap Cal.45', 'RIA Hi Cap Cal.45']},
        {'label': 'RIFLE 5.56MM: M16',         'qs': rifles,  'models': ['M16A1 Rifle 5.56mm']},
        {'label': 'RIFLE 5.56MM: M4',         'qs': rifles,  'models': ['M4 Carbine DSAR-15 5.56mm', 'M4 14.5" DGIS EMTAN 5.56mm']},
        {'label': 'RIFLE 5.56MM: M653',       'qs': rifles,  'models': ['M653 Carbine 5.56mm']},
        {'label': 'RIFLE 7.62: M14',          'qs': rifles,  'models': ['M14 Rifle 7.62mm']},
    ]

    rows = []
    totals = {'stock': 0, 'par': 0, 'tr': 0, 'unserviceable': 0, 'total': 0}

    for nom in NOMENCLATURES:
        qs            = nom['qs'].filter(model__in=nom['models'])
        stock         = qs.filter(item_status__in=['Available', 'Under Maintenance', 'For Turn In']).count()
        par           = qs.filter(item_status='Issued', last_issuance__startswith='PAR').count()
        tr            = qs.filter(item_status='Issued', last_issuance__startswith='TR').count()
        unserviceable = qs.filter(item_condition='Unserviceable').count()
        total         = stock + par + tr

        rows.append({
            'label': nom['label'],
            'stock': stock, 'par': par, 'tr': tr,
            'unserviceable': unserviceable, 'total': total,
        })
        totals['stock']         += stock
        totals['par']           += par
        totals['tr']            += tr
        totals['unserviceable'] += unserviceable
        totals['total']         += total

    return rows, totals


@login_required
def print_transactions(request):
    if not _can_print(request.user):
        messages.error(request, 'You do not have permission to access Print Reports.')
        return redirect('dashboard')
    personnel_id    = request.GET.get('personnel_id')
    txn_type_filter = (request.GET.get('txn_type') or '').strip()     # 'Withdrawal' | 'Return'
    issuance_filter = (request.GET.get('issuance') or '').strip()     # 'TR' | 'PAR'
    range_filter    = (request.GET.get('range') or '').strip().lower()

    transactions = (
        Transaction.objects
        .select_related('personnel', 'pistol', 'rifle')
        .order_by('-timestamp')
    )

    # ── Filter by personnel ────────────────────────────────────────────────────
    if personnel_id:
        try:
            personnel_obj = Personnel.objects.get(Personnel_ID=personnel_id)
            transactions = transactions.filter(personnel=personnel_obj)
        except Personnel.DoesNotExist:
            messages.error(request, 'Personnel not found.')
            return redirect('print_handler:print_transactions')

    # ── Filter by transaction type (Withdrawal / Return) ──────────────────────
    if txn_type_filter in ('Withdrawal', 'Return'):
        transactions = transactions.filter(transaction_type=txn_type_filter)

    # ── Filter by issuance type (TR / PAR) ────────────────────────────────────
    if issuance_filter == 'TR':
        transactions = transactions.filter(issuance_type__startswith='TR')
    elif issuance_filter == 'PAR':
        transactions = transactions.filter(issuance_type__startswith='PAR')

    # ── Date range filter ──────────────────────────────────────────────────────
    range_days = {'day': 1, 'week': 7, 'month': 30}
    if range_filter in range_days:
        since = timezone.now() - timedelta(days=range_days[range_filter])
        transactions = transactions.filter(timestamp__gte=since)

    # ── Summary counts ─────────────────────────────────────────────────────────
    summary_counts = transactions.aggregate(
        total_withdrawals=Count(
            'transaction_id',
            filter=Q(transaction_type='Withdrawal')
        ),
        total_returns=Count(
            'transaction_id',
            filter=Q(transaction_type='Return')
        ),
        tr_withdrawals=Count(
            'transaction_id',
            filter=Q(transaction_type='Withdrawal', issuance_type__startswith='TR')
        ),
        tr_returns=Count(
            'transaction_id',
            filter=Q(transaction_type='Return', issuance_type__startswith='TR')
        ),
        par_withdrawals=Count(
            'transaction_id',
            filter=Q(transaction_type='Withdrawal', issuance_type__startswith='PAR')
        ),
        par_returns=Count(
            'transaction_id',
            filter=Q(transaction_type='Return', issuance_type__startswith='PAR')
        ),
    )

    # ── Daily Firearms Evaluation ──────────────────────────────────────────────
    eval_rows, eval_totals = _firearms_evaluation()

    # ── Armorer: use linked Personnel record; fall back to User profile ──────
    from armguard.apps.personnel.models import Personnel as _Personnel
    from armguard.apps.users.models import SystemSettings as _SysSettings
    _sys = _SysSettings.get()
    _armorer_branch      = _sys.armorer_branch or 'PAF'
    _armorer_designation = 'Armorer'
    try:
        _p = _Personnel.objects.get(user=request.user)
        _mi = f' {_p.middle_initial}.' if _p.middle_initial else ''
        _armorer_name = f'{_p.first_name}{_mi} {_p.last_name}'.upper()
        _armorer_rank = _p.rank
        try:
            _armorer_designation = request.user.profile.role or ('System Administrator' if request.user.is_superuser else 'Armorer')
        except Exception:
            _armorer_designation = 'System Administrator' if request.user.is_superuser else 'Armorer'
    except _Personnel.DoesNotExist:
        # Fall back to the Django User's own name and role
        _full = request.user.get_full_name().strip()
        _armorer_name = _full.upper() if _full else request.user.username.upper()
        _armorer_rank = ''  # no military rank — role goes into designation below
        try:
            _armorer_designation = request.user.profile.role or ('System Administrator' if request.user.is_superuser else 'Armorer')
        except Exception:
            _armorer_designation = 'System Administrator' if request.user.is_superuser else 'Armorer'

    context = {
        'transactions': transactions,
        'personnel_id': personnel_id,
        'selected_txn_type': txn_type_filter,
        'selected_issuance': issuance_filter,
        'selected_range': range_filter,
        'summary_counts': summary_counts,
        # Daily Firearms Evaluation
        'firearms_eval_rows':        eval_rows,
        'firearms_eval_totals':      eval_totals,
        'armorer_name':              _armorer_name,
        'armorer_rank':              _armorer_rank,
        'armorer_branch':            _armorer_branch,
        'armorer_designation':       _armorer_designation,
        'commander_name':            _sys.commander_name,
        'commander_rank':            _sys.commander_rank,
        'commander_branch':          _sys.commander_branch,
        'commander_designation':     _sys.commander_designation or 'Squadron Commander',
        'unit_name':                 _sys.unit_name,
        # Watermark
        'watermark_user':            request.user.get_full_name() or request.user.username,
        'watermark_time':            timezone.localtime().strftime('%Y-%m-%d %H:%M PHT'),
    }
    return render(request, 'print/print_transactions_bare.html' if request.GET.get('bare') else 'print/print_transactions.html', context)


@login_required
def download_transaction_pdf(request, transaction_id):
    """
    Serve the TR (Temporary Receipt) filled PDF for a transaction.
    - TR issuance → fill Temp_Rec.pdf via TransactionFormFiller and serve it
    - PAR issuance → serve the uploaded par_document
    - No issuance type → 400 error
    """
    from django.http import FileResponse

    transaction = get_object_or_404(Transaction, transaction_id=transaction_id)
    issuance = (transaction.issuance_type or '').strip()

    # ── PAR: serve the uploaded signed document ────────────────────────────────
    if issuance.startswith('PAR'):
        if not transaction.par_document:
            messages.error(request, 'No PAR document has been uploaded for this transaction.')
            return redirect('transaction-detail', transaction_id=transaction_id)
        try:
            par_filename = os.path.basename(transaction.par_document.name)
            return serve_pdf(
                request,
                pdf_type=PDF_TYPE_PAR,
                filename=par_filename,
                label=f'PAR #{transaction_id} – {transaction.personnel}',
                apply_watermark=True,
            )
        except Exception as e:
            messages.error(request, f'Error serving PAR document: {e}')
            return redirect('transaction-detail', transaction_id=transaction_id)

    # ── TR: fill and serve Temp_Rec.pdf ───────────────────────────────────────
    if not issuance.startswith('TR'):
        messages.error(request, f'Transaction #{transaction_id} has no issuance type — cannot generate a PDF form.')
        return redirect('transaction-detail', transaction_id=transaction_id)

    # Filename: TR_rank_lastname_transactionID.pdf  (filesystem-safe)
    rank = re.sub(r'[^A-Za-z0-9]', '', transaction.personnel.rank or 'UNK')
    last = re.sub(r'[^A-Za-z0-9]', '', transaction.personnel.last_name or 'Unknown')
    filename = f"TR_{rank}_{last}_{transaction.transaction_id}.pdf"
    output_dir = os.path.join(settings.MEDIA_ROOT, 'TR_PDF')
    output_path = os.path.join(output_dir, filename)

    # Always regenerate fresh so stale cached files never produce blank/extra pages.
    # The filled PDF is written to disk for archival but always served from memory.
    try:
        form_filler = TransactionFormFiller()
        filled_pdf = form_filler.fill_transaction_form(transaction)

        os.makedirs(output_dir, exist_ok=True)
        filled_pdf.seek(0)
        pdf_bytes = filled_pdf.read()

        # Write to disk for archival (overwrites stale cache).
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)

        return serve_pdf_bytes(
            request,
            pdf_bytes=pdf_bytes,
            filename=filename,
            label=f'TR #{transaction_id} – {transaction.personnel}',
            apply_watermark=True,
            extra_headers={'X-Print-Page-Size': 'legal'},
        )

    except Exception as e:
        messages.error(request, f'Error generating TR PDF: {e}')
        return redirect('transaction-detail', transaction_id=transaction_id)


@login_required
def print_transaction_pdf(request, transaction_id):
    """
    Show print-ready page for a transaction PDF.
    - TR → embed the filled Temp_Rec.pdf via pdf_print.html (Legal size)
    - PAR → redirect directly to the par_document PDF URL
    """
    from django.urls import reverse

    transaction = get_object_or_404(Transaction, transaction_id=transaction_id)
    issuance = (transaction.issuance_type or '').strip()

    if issuance.startswith('PAR'):
        # Redirect to the download view which will serve the PAR document
        return redirect(
            reverse('print_handler:download_transaction_pdf', kwargs={'transaction_id': transaction_id})
        )

    if not issuance.startswith('TR'):
        messages.error(request, f'Transaction #{transaction_id} has no issuance type — cannot print a PDF form.')
        return redirect('transaction-detail', transaction_id=transaction_id)

    pdf_url = reverse('print_handler:download_transaction_pdf', kwargs={'transaction_id': transaction_id})
    return render(request, 'print/pdf_print.html', {
        'transaction': transaction,
        'pdf_url': pdf_url,
    })


# ---------------------------------------------------------------------------
# Personnel ID Card Print Manager
# ---------------------------------------------------------------------------

@login_required
def serve_id_card_image(request, personnel_id, side):
    """
    Serve an ID card PNG file directly through Django (works in production
    without relying on nginx media-file configuration).
    side: 'front' | 'back' | 'combined'
    """
    from django.http import FileResponse, Http404
    from pathlib import Path
    # Validate personnel record exists before serving any file (prevents enumeration)
    get_object_or_404(Personnel, Personnel_ID=personnel_id)
    if side == 'front':
        filename = f"{personnel_id}_front.png"
    elif side == 'back':
        filename = f"{personnel_id}_back.png"
    else:
        filename = f"{personnel_id}.png"

    filepath = Path(settings.MEDIA_ROOT).resolve() / 'personnel_id_cards' / filename
    if not filepath.exists():
        raise Http404('ID card image not found')
    return FileResponse(open(filepath, 'rb'), content_type='image/png')


@login_required
@user_passes_test(lambda u: u.is_superuser)
def id_card_diagnostics(request):
    """Superuser-only diagnostic page — shows exactly what paths Django is checking."""
    from django.http import HttpResponse
    import glob

    media_root = settings.MEDIA_ROOT
    id_cards_dir = os.path.join(media_root, 'personnel_id_cards')

    # List actual files on disk
    actual_files = []
    if os.path.isdir(id_cards_dir):
        actual_files = sorted(os.listdir(id_cards_dir))

    # Check each personnel — reuse the actual_files set already collected above
    existing_set = set(actual_files)
    rows = []
    for p in Personnel.objects.order_by('last_name')[:5]:
        front_path = os.path.join(id_cards_dir, f"{p.Personnel_ID}_front.png")
        combined_path = os.path.join(id_cards_dir, f"{p.Personnel_ID}.png")
        front_exists    = f"{p.Personnel_ID}_front.png" in existing_set
        combined_exists = f"{p.Personnel_ID}.png" in existing_set
        rows.append(
            f"<tr><td>{p.Personnel_ID}</td>"
            f"<td>{front_path}</td>"
            f"<td>{'EXISTS' if front_exists else 'MISSING'}</td>"
            f"<td>{combined_path}</td>"
            f"<td>{'EXISTS' if combined_exists else 'MISSING'}</td></tr>"
        )

    html = f"""
    <html><head><title>ID Card Diagnostics</title>
    <style>body{{font-family:monospace;padding:2rem}}table{{border-collapse:collapse}}
    td,th{{border:1px solid #ccc;padding:6px 12px}}</style></head><body>
    <h2>ID Card Path Diagnostics</h2>
    <p><strong>MEDIA_ROOT</strong> = <code>{media_root}</code></p>
    <p><strong>personnel_id_cards dir</strong> = <code>{id_cards_dir}</code></p>
    <p><strong>Dir exists?</strong> {os.path.isdir(id_cards_dir)}</p>
    <p><strong>Files in dir ({len(actual_files)} total)</strong></p>
    <pre>{'<br>'.join(actual_files[:30]) or '(empty)'}</pre>
    <h3>First 5 personnel path check:</h3>
    <table><tr><th>ID</th><th>Front path</th><th>Front</th><th>Combined path</th><th>Combined</th></tr>
    {''.join(rows)}
    </table>
    </body></html>
    """
    return HttpResponse(html)


def _id_card_img_url(request, personnel_id, side='front'):
    """Return the URL for an ID card image served through the Django view."""
    from django.urls import reverse
    return reverse('print_handler:serve_id_card_image',
                   kwargs={'personnel_id': personnel_id, 'side': side})


@login_required
def print_id_cards(request):
    """
    Personnel ID Card Print Manager.
    Lists all active personnel, shows their ID card thumbnail,
    and allows single/bulk printing and card regeneration.
    """
    search_q = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip().lower()  # 'officer' | 'enlisted' | ''

    _OFFICER_RANKS = set(dict(Personnel.RANKS_OFFICER).keys())
    _ENLISTED_RANKS = set(dict(Personnel.RANKS_ENLISTED).keys())

    personnel_qs = Personnel.objects.filter(status='Active').order_by('last_name', 'first_name')
    if search_q:
        from django.db.models import Q as DQ
        personnel_qs = personnel_qs.filter(
            DQ(last_name__icontains=search_q) |
            DQ(first_name__icontains=search_q) |
            DQ(Personnel_ID__icontains=search_q) |
            DQ(rank__icontains=search_q)
        )
    if category == 'officer':
        personnel_qs = personnel_qs.filter(rank__in=_OFFICER_RANKS)
    elif category == 'enlisted':
        personnel_qs = personnel_qs.filter(rank__in=_ENLISTED_RANKS)

    # PERF: one os.listdir() to build membership sets instead of N*2 os.path.exists() calls
    id_cards_dir = os.path.join(settings.MEDIA_ROOT, 'personnel_id_cards')
    existing_cards = set(os.listdir(id_cards_dir)) if os.path.isdir(id_cards_dir) else set()

    personnel_cards = []
    for p in personnel_qs:
        has_front    = f"{p.Personnel_ID}_front.png" in existing_cards
        has_combined = f"{p.Personnel_ID}.png" in existing_cards
        has_card = has_front or has_combined
        if has_card:
            side = 'front' if has_front else 'combined'
            thumb_url = _id_card_img_url(request, p.Personnel_ID, side)
        else:
            thumb_url = None

        personnel_cards.append({
            'personnel': p,
            'has_card': has_card,
            'thumb_url': thumb_url,
        })

    total = len(personnel_cards)
    with_card = sum(1 for c in personnel_cards if c['has_card'])

    _officer_ranks = {'2LT','1LT','CPT','MAJ','LTCOL','COL','BGEN','MGEN','LTGEN','GEN'}
    active_qs = Personnel.objects.filter(status='Active')
    officers_count = active_qs.filter(rank__in=_officer_ranks).count()
    enlisted_count = active_qs.exclude(rank__in=_officer_ranks).count()

    context = {
        'personnel_cards': personnel_cards,
        'search_q': search_q,
        'category': category,
        'total': total,
        'with_card': with_card,
        'without_card': total - with_card,
        'officers_count': officers_count,
        'enlisted_count': enlisted_count,
    }
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'print/print_id_cards_grid.html', context)
    return render(request, 'print/print_id_cards.html', context)


@login_required
@require_POST
def generate_missing_cards(request):
    """
    Bulk-generate ID cards for active personnel.
    POST body param  force=1  → regenerate ALL cards (even those that already exist).
    Default (force=0) → generate only personnel who have no card file yet.
    Returns JSON {generated, skipped, errors}
    """
    if not _can_edit(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    from utils.personnel_id_card_generator import generate_personnel_id_card

    force = request.POST.get('force', '0') == '1'

    generated = 0
    skipped   = 0
    errors    = []

    # PERF: one os.listdir() instead of N*2 os.path.exists() calls
    id_cards_dir_bulk = os.path.join(settings.MEDIA_ROOT, 'personnel_id_cards')
    existing_bulk = set(os.listdir(id_cards_dir_bulk)) if os.path.isdir(id_cards_dir_bulk) else set()

    personnel_qs = Personnel.objects.filter(status='Active')
    for p in personnel_qs:
        has_card = f"{p.Personnel_ID}_front.png" in existing_bulk or f"{p.Personnel_ID}.png" in existing_bulk
        if not force and has_card:
            skipped += 1
            continue
        try:
            generate_personnel_id_card(p)
            generated += 1
        except Exception as exc:
            errors.append({'id': p.Personnel_ID, 'name': str(p), 'error': str(exc)})

    return JsonResponse({'success': True, 'generated': generated, 'skipped': skipped, 'errors': errors})


@login_required
@require_POST
def regenerate_id_card(request, personnel_id):
    """Regenerate the ID card PNG for a single personnel (AJAX POST)."""
    if not _can_edit(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    try:
        personnel = Personnel.objects.get(Personnel_ID=personnel_id)
    except Personnel.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Personnel not found'}, status=404)

    try:
        from utils.personnel_id_card_generator import generate_personnel_id_card
        paths = generate_personnel_id_card(personnel)
        side = 'front' if paths.get('front') else 'combined'
        thumb_url = _id_card_img_url(request, personnel_id, side)
        return JsonResponse({'success': True, 'thumb_url': thumb_url})
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
def print_id_cards_view(request):
    """
    Print-ready page for selected (or all) personnel ID cards.
    Accepts ?ids=PO-xxx,PE-xxx,... or ?all=1
    Optional ?side=front|back|both (default: both)
    """
    if not _can_print(request.user):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    ids_param = request.GET.get('ids', '')
    show_all  = request.GET.get('all', '')
    side      = request.GET.get('side', 'both').lower()
    if side not in ('front', 'back', 'both'):
        side = 'both'

    if show_all:
        personnel_qs = Personnel.objects.filter(status='Active').order_by('last_name', 'first_name')
    elif ids_param:
        id_list = [i.strip() for i in ids_param.split(',') if i.strip()]
        personnel_qs = Personnel.objects.filter(Personnel_ID__in=id_list, status='Active')
    else:
        personnel_qs = Personnel.objects.none()

    cards = []
    for p in personnel_qs:
        front_abs    = os.path.join(settings.MEDIA_ROOT, 'personnel_id_cards', f"{p.Personnel_ID}_front.png")
        back_abs     = os.path.join(settings.MEDIA_ROOT, 'personnel_id_cards', f"{p.Personnel_ID}_back.png")
        combined_abs = os.path.join(settings.MEDIA_ROOT, 'personnel_id_cards', f"{p.Personnel_ID}.png")

        if os.path.exists(front_abs):
            front_url = _id_card_img_url(request, p.Personnel_ID, 'front')
        elif os.path.exists(combined_abs):
            front_url = _id_card_img_url(request, p.Personnel_ID, 'combined')
        else:
            front_url = None

        back_url = _id_card_img_url(request, p.Personnel_ID, 'back') if os.path.exists(back_abs) else None

        if front_url:
            cards.append({'personnel': p, 'front_url': front_url, 'back_url': back_url})

    return render(request, 'print/print_id_cards_printview.html', {'cards': cards, 'side': side})


# ---------------------------------------------------------------------------
# Mission Order (MO) PDF Viewer
# ---------------------------------------------------------------------------

@login_required
def download_mo_pdf(request, transaction_id):
    """
    Serve the Mission Order PDF attached to a transaction.

    The MO document is an uploaded signed PDF stored in media/MO_PDF/.
    Access is authenticated, audited, and routed through the centralized
    pdf_viewer so all PDF security guarantees apply.

    Expects Transaction.mo_document (FileField) to be populated.
    Returns a 404-redirect if the field is not yet present on the model
    or no document has been uploaded.
    """
    transaction = get_object_or_404(Transaction, transaction_id=transaction_id)

    mo_doc = getattr(transaction, 'mo_document', None)
    if not mo_doc:
        messages.error(request, 'No Mission Order document has been uploaded for this transaction.')
        return redirect('transaction-detail', transaction_id=transaction_id)

    try:
        mo_filename = os.path.basename(mo_doc.name)
        return serve_pdf(
            request,
            pdf_type=PDF_TYPE_MO,
            filename=mo_filename,
            label=f'MO #{transaction_id} – {transaction.personnel}',
            apply_watermark=True,
        )
    except Exception as e:
        messages.error(request, f'Error serving Mission Order document: {e}')
        return redirect('transaction-detail', transaction_id=transaction_id)


# ---------------------------------------------------------------------------
# Daily Report PDF — generated from the firearms evaluation data
# ---------------------------------------------------------------------------

@login_required
def download_daily_report_pdf(request):
    """
    Generate and serve the Daily Firearms Evaluation as a PDF.

    Builds the report from live DB data (same _firearms_evaluation() query
    used by the HTML print view) and streams it as a PDF via the centralized
    pdf_viewer utility.

    Requires PyMuPDF (fitz).  Falls back to a plain-text error response if
    PyMuPDF is not available.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return HttpResponse(
            'PDF generation requires PyMuPDF.  Install it with: pip install pymupdf',
            content_type='text/plain',
            status=503,
        )

    from django.utils import timezone as dj_tz
    from utils.pdf_viewer import serve_pdf_bytes

    eval_rows, eval_totals = _firearms_evaluation()

    now      = dj_tz.localtime(dj_tz.now())
    date_str = now.strftime('%d %B %Y')
    time_str = now.strftime('%H:%M')

    # ── build PDF with PyMuPDF ────────────────────────────────────────────────
    doc  = fitz.open()
    page = doc.new_page(width=595, height=842)   # A4 portrait

    # ── helpers ───────────────────────────────────────────────────────────────
    BLACK  = (0, 0, 0)
    WHITE  = (1, 1, 1)
    NAVY   = (0.08, 0.20, 0.40)
    ORANGE = (0.95, 0.55, 0.10)

    def _text(pt, txt, size=10, color=BLACK, bold=False):
        page.insert_text(
            fitz.Point(*pt), txt,
            fontname='helv-bold' if bold else 'helv',
            fontsize=size,
            color=color,
        )

    def _rect_fill(rect, color):
        page.draw_rect(fitz.Rect(*rect), color=color, fill=color)

    # ── system settings (loaded early so unit_name is available for header) ──
    from armguard.apps.users.models import SystemSettings as _SysSettings2
    _sys2 = _SysSettings2.get()

    # ── header banner ────────────────────────────────────────────────────────
    _rect_fill((30, 22, 565, 58), NAVY)
    _text((35, 48), _sys2.unit_name or 'PHILIPPINE AIR FORCE — 950th CEWW', size=13, color=WHITE, bold=True)
    _rect_fill((30, 59, 565, 70), ORANGE)
    _text((35, 83), 'DAILY FIREARMS EVALUATION REPORT', size=11, color=BLACK, bold=True)
    _text((35, 97), f'Date: {date_str}   Time: {time_str}', size=9, color=BLACK)

    # ── table header ─────────────────────────────────────────────────────────
    cols = [35, 200, 280, 340, 400, 465, 530]
    heads = ['NOMENCLATURE', 'STOCK', 'PAR', 'TR', 'UNSVC', 'TOTAL']
    _rect_fill((30, 112, 565, 128), NAVY)
    for idx, (hx, label) in enumerate(zip(cols, heads)):
        _text((hx + 2, 124), label, size=8, color=WHITE, bold=True)

    # ── table rows ────────────────────────────────────────────────────────────
    y = 140
    for i, row in enumerate(eval_rows):
        if i % 2 == 0:
            _rect_fill((30, y - 12, 565, y + 4), (0.94, 0.96, 0.99))
        values = [row['label'], str(row['stock']), str(row['par']),
                  str(row['tr']), str(row['unserviceable']), str(row['total'])]
        for hx, val in zip(cols, values):
            _text((hx + 2, y), val, size=8)
        y += 18

    # ── totals row ────────────────────────────────────────────────────────────
    _rect_fill((30, y - 4, 565, y + 14), NAVY)
    totals_values = ['TOTAL', str(eval_totals['stock']), str(eval_totals['par']),
                     str(eval_totals['tr']), str(eval_totals['unserviceable']),
                     str(eval_totals['total'])]
    for hx, val in zip(cols, totals_values):
        _text((hx + 2, y + 10), val, size=9, color=WHITE, bold=True)

    y += 38

    # ── signature block ───────────────────────────────────────────────────────
    from armguard.apps.personnel.models import Personnel as _Personnel
    _armorer_designation = 'Armorer'
    try:
        _p = _Personnel.objects.get(user=request.user)
        _mi = f' {_p.middle_initial}.' if _p.middle_initial else ''
        _armorer_name = f'{_p.first_name}{_mi} {_p.last_name}'.upper()
        _armorer_rank = _p.rank
        try:
            _armorer_designation = request.user.profile.role or ('System Administrator' if request.user.is_superuser else 'Armorer')
        except Exception:
            _armorer_designation = 'System Administrator' if request.user.is_superuser else 'Armorer'
    except _Personnel.DoesNotExist:
        _full = request.user.get_full_name().strip()
        _armorer_name = _full.upper() if _full else request.user.username.upper()
        _armorer_rank = ''
        try:
            _armorer_designation = request.user.profile.role or ('System Administrator' if request.user.is_superuser else 'Armorer')
        except Exception:
            _armorer_designation = 'System Administrator' if request.user.is_superuser else 'Armorer'
    _commander_name = _sys2.commander_name
    _commander_rank = _sys2.commander_rank

    _text((60, y + 20),  f'{_armorer_rank} {_armorer_name}'.strip() or 'ARMORER',       size=9, bold=True)
    _text((60, y + 32),  _armorer_designation,                                            size=8)
    _text((350, y + 20), f'{_commander_rank} {_commander_name}'.strip() or 'COMMANDER',  size=9, bold=True)
    _text((350, y + 32), _sys2.commander_designation or 'Commander',                      size=8)

    pdf_bytes = doc.tobytes(deflate=True)
    doc.close()

    filename = f'Daily_Firearms_Evaluation_{now.strftime("%Y%m%d_%H%M")}.pdf'

    return serve_pdf_bytes(
        request,
        pdf_bytes=pdf_bytes,
        filename=filename,
        label=f'Daily Firearms Evaluation – {date_str}',
        apply_watermark=True,
    )
