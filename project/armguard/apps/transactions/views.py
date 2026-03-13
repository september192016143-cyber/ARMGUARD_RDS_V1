from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.db.models import Q, Subquery, OuterRef
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.core.cache import cache
from .models import Transaction, TransactionLogs
from .forms import WithdrawalReturnTransactionForm
from utils.throttle import ratelimit
# H1 FIX: Import shared permission helper instead of duplicating it here.
from armguard.utils.permissions import can_create_transaction as _can_create_transaction


class TransactionListView(LoginRequiredMixin, ListView):
    model = Transaction
    template_name = 'transactions/transaction_list.html'
    context_object_name = 'transactions'
    paginate_by = 25

    def get_queryset(self):
        # M6: Return transactions now carry their own issuance_type (copied from the
        # matching Withdrawal at save time), so no Subquery annotation is needed.
        # M6B: For legacy Return rows saved before M6, fall back to the most-recent
        # prior Withdrawal by the same personnel via a correlated subquery.
        _prior_withdrawal_issuance = (
            Transaction.objects
            .filter(
                transaction_type='Withdrawal',
                personnel=OuterRef('personnel'),
                timestamp__lt=OuterRef('timestamp'),
            )
            .exclude(issuance_type__isnull=True)
            .exclude(issuance_type='')
            .order_by('-timestamp')
            .values('issuance_type')[:1]
        )
        qs = (
            Transaction.objects
            .select_related('personnel', 'pistol', 'rifle')
            .annotate(effective_issuance=Coalesce('issuance_type', Subquery(_prior_withdrawal_issuance)))
            .order_by('-timestamp')
        )
        q = self.request.GET.get('q', '').strip()
        txn_type = self.request.GET.get('type', '').strip()
        issuance = self.request.GET.get('issuance', '').strip()
        if q:
            qs = qs.filter(
                Q(personnel__first_name__icontains=q) |
                Q(personnel__last_name__icontains=q) |
                Q(personnel__Personnel_ID__icontains=q) |
                Q(transaction_id__icontains=q)
            )
        if txn_type in ('Withdrawal', 'Return'):
            qs = qs.filter(transaction_type=txn_type)
        if issuance == 'TR':
            qs = qs.filter(effective_issuance__startswith='TR')
        elif issuance == 'PAR':
            qs = qs.filter(effective_issuance__startswith='PAR')
        date_from = self.request.GET.get('date_from', '').strip()
        date_to   = self.request.GET.get('date_to',   '').strip()
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_type'] = self.request.GET.get('type', '')
        ctx['selected_issuance'] = self.request.GET.get('issuance', '')
        ctx['date_from'] = self.request.GET.get('date_from', '')
        ctx['date_to']   = self.request.GET.get('date_to',   '')
        ctx['now'] = timezone.now()
        return ctx

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render(self.request, 'transactions/transaction_rows.html', context)
        return super().render_to_response(context, **response_kwargs)


class TransactionDetailView(LoginRequiredMixin, DetailView):
    model = Transaction
    template_name = 'transactions/transaction_detail.html'
    context_object_name = 'transaction'
    pk_url_kwarg = 'transaction_id'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        transaction = ctx['transaction']
        original_issuance_type = None
        if transaction.transaction_type == 'Return':
            from .models import TransactionLogs
            from django.db.models import Q
            # Build an OR query — any log where this return transaction is referenced
            q = Q()
            if transaction.pistol:
                q |= Q(return_pistol_transaction_id=transaction)
            if transaction.rifle:
                q |= Q(return_rifle_transaction_id=transaction)
            if transaction.pistol_magazine:
                q |= Q(return_pistol_magazine_transaction_id=transaction)
            if transaction.rifle_magazine:
                q |= Q(return_rifle_magazine_transaction_id=transaction)
            if transaction.pistol_ammunition:
                q |= Q(return_pistol_ammunition_transaction_id=transaction)
            if transaction.rifle_ammunition:
                q |= Q(return_rifle_ammunition_transaction_id=transaction)
            if transaction.pistol_holster_quantity:
                q |= Q(return_pistol_holster_transaction_id=transaction)
            if transaction.magazine_pouch_quantity:
                q |= Q(return_magazine_pouch_transaction_id=transaction)
            if transaction.rifle_sling_quantity:
                q |= Q(return_rifle_sling_transaction_id=transaction)
            if transaction.bandoleer_quantity:
                q |= Q(return_bandoleer_transaction_id=transaction)
            if q:
                log = TransactionLogs.objects.select_related(
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
                ).filter(
                    personnel_id=transaction.personnel
                ).filter(q).first()
                if log:
                    # Prefer the stored issuance_type on the log; fall back to reading
                    # directly from whichever withdrawal transaction FK is populated.
                    original_issuance_type = log.issuance_type
                    if not original_issuance_type:
                        for fk_attr in [
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
                        ]:
                            w_txn = getattr(log, fk_attr, None)
                            if w_txn and getattr(w_txn, 'issuance_type', None):
                                original_issuance_type = w_txn.issuance_type
                                break
        ctx['original_issuance_type'] = original_issuance_type
        ctx['now'] = timezone.now()
        return ctx


@login_required
def create_transaction(request):
    if not _can_create_transaction(request.user):
        return HttpResponseForbidden("You do not have permission to create transactions.")
    if request.method == 'POST':
        form = WithdrawalReturnTransactionForm(request.POST, request.FILES)
        if form.is_valid():
            txn = form.save(commit=False)
            txn.transaction_personnel = request.user.get_full_name() or request.user.username
            txn.save(user=request.user)
            # Invalidate dashboard caches so counts and table reflect the new transaction immediately.
            from django.utils import timezone as _tz
            cache.delete(f'dashboard_stats_{_tz.localdate()}')
            cache.delete('dashboard_inventory_tables')
            messages.success(request, f'Transaction #{txn.transaction_id} recorded successfully.')
            return redirect('transaction-detail', transaction_id=txn.transaction_id)
    else:
        form = WithdrawalReturnTransactionForm()
    return render(request, 'transactions/transaction_form.html', {'form': form})


# Legacy stub kept for import compatibility
def create_withdrawal_return_transaction(request):
    return create_transaction(request)


@login_required
@require_POST
def tr_preview(request):
    """
    Validate the in-progress transaction form exactly as Submit does,
    then generate and return a filled TR PDF preview without saving.
    """
    from types import SimpleNamespace
    from django.utils import timezone
    from armguard.apps.print.pdf_filler.form_filler import TransactionFormFiller

    # Run the exact same form validation as create_transaction/Submit
    form = WithdrawalReturnTransactionForm(request.POST, request.FILES)
    if not form.is_valid():
        field_errors = {}
        non_field_errors = []
        for field, errs in form.errors.items():
            if field == '__all__':
                non_field_errors.extend([str(e) for e in errs])
            else:
                label = form.fields[field].label if field in form.fields else field
                field_errors[field] = [str(e) for e in errs]
                non_field_errors.extend([f"{label}: {e}" for e in errs])
        return JsonResponse({'field_errors': field_errors, 'non_field_errors': non_field_errors}, status=400)

    # Form is valid — extract the cleaned (possibly auto-filled) data
    cd = form.cleaned_data
    personnel = cd['personnel']
    pistol     = cd.get('pistol')
    rifle      = cd.get('rifle')

    purpose = cd.get('purpose') or ''

    # Try to find the armorer's Personnel record via the User OneToOne link
    try:
        from armguard.apps.personnel.models import Personnel as PersonnelModel
        armorer_personnel = PersonnelModel.objects.get(user=request.user)
    except Exception:
        armorer_personnel = None

    def _safe_int(val):
        try:
            return int(val or 0)
        except (TypeError, ValueError):
            return 0

    mock_txn = SimpleNamespace(
        transaction_id='PREVIEW',
        transaction_type=cd.get('transaction_type', 'Withdrawal'),
        issuance_type='TR (Temporary Receipt)',
        personnel=personnel,
        pistol=pistol,
        rifle=rifle,
        pistol_magazine_quantity=_safe_int(cd.get('pistol_magazine_quantity')),
        rifle_magazine_quantity=_safe_int(cd.get('rifle_magazine_quantity')),
        pistol_ammunition_quantity=_safe_int(cd.get('pistol_ammunition_quantity')),
        rifle_ammunition_quantity=_safe_int(cd.get('rifle_ammunition_quantity')),
        purpose=purpose,
        timestamp=timezone.now(),
        transaction_personnel=request.user.get_full_name() or request.user.username,
        armorer_personnel=armorer_personnel,
        pistol_holster_quantity=_safe_int(cd.get('pistol_holster_quantity')),
        magazine_pouch_quantity=_safe_int(cd.get('magazine_pouch_quantity')),
        rifle_sling_quantity=_safe_int(cd.get('rifle_sling_quantity')),
        bandoleer_quantity=_safe_int(cd.get('bandoleer_quantity')),
        notes=cd.get('notes', ''),
        return_by=cd.get('return_by') or (timezone.now() + __import__('datetime').timedelta(hours=24)),
    )

    filler = TransactionFormFiller()
    try:
        pdf_bytes = filler.fill_transaction_form(mock_txn)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('TR preview PDF generation failed')
        return JsonResponse(
            {'field_errors': {}, 'non_field_errors': ['PDF generation failed. Please try again.']},
            status=500,
        )

    response = HttpResponse(pdf_bytes.read(), content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="TR_Preview.pdf"'
    return response


@login_required
@require_GET
@ratelimit(rate='60/m')
def personnel_status(request):
    """
    Real-time lookup: return what a selected personnel currently has issued
    and whether they're allowed to withdraw a pistol / rifle.
    GET ?personnel_id=<pk>
    """
    from armguard.apps.personnel.models import Personnel
    pk = request.GET.get('personnel_id', '').strip()
    if not pk:
        return JsonResponse({'error': 'No personnel_id supplied.'}, status=400)
    try:
        p = Personnel.objects.get(pk=pk)
    except Personnel.DoesNotExist:
        return JsonResponse({'error': 'Personnel not found.'}, status=404)

    data = {
        'name': f"{p.rank} {p.first_name} {p.last_name}",
        'status': p.status,
        'pistol_issued': p.pistol_item_issued or None,
        'rifle_issued': p.rifle_item_issued or None,
        'can_withdraw_pistol': not p.has_pistol_issued(),
        'can_withdraw_rifle': not p.has_rifle_issued(),
        'pistol_mag_issued': p.pistol_magazine_item_issued or None,
        'pistol_mag_qty': p.pistol_magazine_item_issued_quantity or None,
        'rifle_mag_issued': p.rifle_magazine_item_issued or None,
        'rifle_mag_qty': p.rifle_magazine_item_issued_quantity or None,
        'pistol_ammo_issued': p.pistol_ammunition_item_issued or None,
        'pistol_ammo_qty': p.pistol_ammunition_item_issued_quantity or None,
        'rifle_ammo_issued': p.rifle_ammunition_item_issued or None,
        'rifle_ammo_qty': p.rifle_ammunition_item_issued_quantity or None,
        'holster_issued': p.pistol_holster_issued or None,
        'holster_qty': p.pistol_holster_issued_quantity or None,
        'mag_pouch_issued': p.magazine_pouch_issued or None,
        'mag_pouch_qty': p.magazine_pouch_issued_quantity or None,
        'rifle_sling_issued': p.rifle_sling_issued or None,
        'rifle_sling_qty': p.rifle_sling_issued_quantity or None,
        'bandoleer_issued': p.bandoleer_issued or None,
        'bandoleer_qty': p.bandoleer_issued_quantity or None,
    }
    # ID card front image
    import os
    from django.conf import settings as _settings
    front_rel = f'personnel_id_cards/{p.pk}_front.png'
    if os.path.exists(os.path.join(_settings.MEDIA_ROOT, front_rel)):
        data['id_card_front_url'] = request.build_absolute_uri(_settings.MEDIA_URL + front_rel)
    else:
        data['id_card_front_url'] = None
    return JsonResponse(data)


@login_required
@require_GET
@ratelimit(rate='60/m')
def item_status_check(request):
    """
    Real-time lookup: return availability/status of a pistol or rifle.
    GET ?type=pistol&item_id=<pk>  OR  ?type=rifle&item_id=<pk>
    """
    from armguard.apps.inventory.models import Pistol, Rifle
    item_type = request.GET.get('type', '').strip()
    item_id   = request.GET.get('item_id', '').strip()
    if not item_id:
        return JsonResponse({'error': 'No item_id supplied.'}, status=400)
    try:
        if item_type == 'pistol':
            item = Pistol.objects.get(pk=item_id)
        elif item_type == 'rifle':
            item = Rifle.objects.get(pk=item_id)
        else:
            return JsonResponse({'error': 'type must be pistol or rifle.'}, status=400)
    except (Pistol.DoesNotExist, Rifle.DoesNotExist):
        return JsonResponse({'error': 'Item not found.'}, status=404)

    ok, reason = item.can_be_withdrawn()
    data = {
        'item_id': item.item_id,
        'model': item.model,
        'serial_number': item.serial_number,
        'item_status': item.item_status,
        'available': ok,
        'reason': reason,
        'issued_to': item.item_issued_to_id or None,
        'item_tag_url': request.build_absolute_uri(item.item_tag.url) if item.item_tag else None,
        'serial_image_url': request.build_absolute_uri(item.serial_image.url) if item.serial_image else None,
    }
    return JsonResponse(data)


@login_required
@require_GET
def overdue_tr_check(request):
    """
    Returns open/partially-returned TR logs grouped into two tiers:
      - overdue:  return_by has already passed
      - warning:  return_by is within the next 2 hours
    Falls back to withdraw_timestamp + 24 h for legacy records that have no return_by.
    Polled by base.js every 5 minutes to drive overdue/warning notifications.
    """
    from django.utils import timezone
    from datetime import timedelta

    WITHDRAWAL_TXN_FK_FIELDS = [
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
    WITHDRAW_TS_FIELDS = [
        'withdraw_pistol_timestamp',
        'withdraw_rifle_timestamp',
        'withdraw_pistol_magazine_timestamp',
        'withdraw_rifle_magazine_timestamp',
        'withdraw_pistol_ammunition_timestamp',
        'withdraw_rifle_ammunition_timestamp',
        'withdraw_pistol_holster_timestamp',
        'withdraw_magazine_pouch_timestamp',
        'withdraw_rifle_sling_timestamp',
        'withdraw_bandoleer_timestamp',
    ]

    logs = (
        TransactionLogs.objects
        .filter(
            issuance_type='TR (Temporary Receipt)',
            log_status__in=['Open', 'Partially Returned'],
        )
        .select_related('personnel_id', *WITHDRAWAL_TXN_FK_FIELDS)
    )

    now = timezone.now()
    WARNING_WINDOW = timedelta(hours=2)

    overdue_list = []
    warning_list = []

    for log in logs:
        # Gather return_by from all withdrawal Transaction FKs on this log
        return_by_values = [
            txn.return_by
            for field in WITHDRAWAL_TXN_FK_FIELDS
            for txn in [getattr(log, field)]
            if txn is not None and getattr(txn, 'return_by', None)
        ]

        if return_by_values:
            deadline = min(return_by_values)
        else:
            # Legacy fallback: use earliest withdrawal timestamp + 24 h
            timestamps = [
                getattr(log, f) for f in WITHDRAW_TS_FIELDS
                if getattr(log, f) is not None
            ]
            if not timestamps:
                continue
            deadline = min(timestamps) + timedelta(hours=24)

        p = log.personnel_id
        personnel_name = ' '.join(filter(None, [p.rank, p.first_name, p.last_name])) if p else 'Unknown'

        items = []
        if log.withdraw_pistol_id:              items.append('Pistol')
        if log.withdraw_rifle_id:               items.append('Rifle')
        if log.withdraw_pistol_magazine_id:     items.append('Pistol Mag')
        if log.withdraw_rifle_magazine_id:      items.append('Rifle Mag')
        if log.withdraw_pistol_ammunition_id:   items.append('Pistol Ammo')
        if log.withdraw_rifle_ammunition_id:    items.append('Rifle Ammo')
        if log.withdraw_pistol_holster_quantity:  items.append('Pistol Holster')
        if log.withdraw_magazine_pouch_quantity:  items.append('Mag Pouch')
        if log.withdraw_rifle_sling_quantity:     items.append('Rifle Sling')
        if log.withdraw_bandoleer_quantity:       items.append('Bandoleer')

        # First non-null withdrawal transaction FK → use its ID for a direct detail link
        txn_id = None
        for field in WITHDRAWAL_TXN_FK_FIELDS:
            txn = getattr(log, field)
            if txn is not None:
                txn_id = str(txn.transaction_id)
                break

        entry = {
            'id':             log.record_id,
            'transaction_id': txn_id,
            'personnel':      personnel_name,
            'items':          items,
            'status':         log.log_status,
            'return_by':      deadline.isoformat(),
        }

        if deadline <= now:
            entry['hours_overdue'] = round((now - deadline).total_seconds() / 3600, 1)
            overdue_list.append(entry)
        elif (deadline - now) <= WARNING_WINDOW:
            entry['minutes_left'] = round((deadline - now).total_seconds() / 60)
            warning_list.append(entry)

    return JsonResponse({'overdue': overdue_list, 'warning': warning_list})
