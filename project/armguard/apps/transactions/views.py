from django.shortcuts import render, redirect, get_object_or_404
import json
import logging
from django.contrib import messages
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.db.models import Q, Subquery, OuterRef, Case, When, F
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.core.cache import cache
from .models import Transaction, TransactionLogs
from .forms import WithdrawalReturnTransactionForm
from utils.throttle import ratelimit
# H1 FIX: Import per-module permission helpers.
from armguard.utils.permissions import (
    can_view_transactions as _can_view_transactions,
    can_create_transaction as _can_create_transaction,
)

_logger = logging.getLogger(__name__)

# Maximum allowed size for a single discrepancy photo upload.
_DISC_IMAGE_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


def _validate_discrepancy_image(f):
    """
    SECURITY FIX: Validate a discrepancy image upload against MIME magic bytes
    and a maximum file-size cap before it is stored.  The HTML accept="image/*"
    attribute is client-side only and trivially bypassed.

    Returns the file object unchanged if it passes all checks, or None if it
    fails.  Failures are logged as warnings but never raise — a bad image must
    never block the underlying Return transaction.

    Allowed formats: JPEG, PNG, GIF, WebP.
    """
    if f is None:
        return None
    if f.size > _DISC_IMAGE_MAX_BYTES:
        _logger.warning(
            'Discrepancy image rejected (size %d > %d bytes): %r',
            f.size, _DISC_IMAGE_MAX_BYTES, getattr(f, 'name', ''),
        )
        return None
    magic = f.read(12)
    f.seek(0)
    is_jpeg = magic[:3] == b'\xff\xd8\xff'
    is_png  = magic[:8] == b'\x89PNG\r\n\x1a\n'
    is_gif  = magic[:6] in (b'GIF87a', b'GIF89a')
    is_webp = magic[:4] == b'RIFF' and magic[8:12] == b'WEBP'
    if not (is_jpeg or is_png or is_gif or is_webp):
        _logger.warning(
            'Discrepancy image rejected (unrecognised magic bytes %r): %r',
            magic[:4], getattr(f, 'name', ''),
        )
        return None
    return f


class TransactionListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Transaction
    template_name = 'transactions/transaction_list.html'
    context_object_name = 'transactions'
    paginate_by = 25

    def test_func(self):
        return _can_view_transactions(self.request.user)

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
        # For Return rows: look up the most-recent prior Withdrawal's return_by
        # for the same personnel AND the same firearm (pistol or rifle) so we
        # always show the deadline for the correct specific weapon.
        _withdrawal_return_by = (
            Transaction.objects
            .filter(
                transaction_type='Withdrawal',
                personnel=OuterRef('personnel'),
                timestamp__lt=OuterRef('timestamp'),
            )
            .filter(
                Q(pistol_id=OuterRef('pistol_id')) | Q(rifle_id=OuterRef('rifle_id'))
            )
            .order_by('-timestamp')
            .values('return_by')[:1]
        )
        # For Withdrawal rows: find the timestamp of the matching Return so the
        # Returned column shows when the item was actually handed back.
        _pistol_returned_ts = (
            Transaction.objects
            .filter(
                transaction_type='Return',
                personnel=OuterRef('personnel'),
                pistol_id=OuterRef('pistol_id'),
                timestamp__gt=OuterRef('timestamp'),
            )
            .order_by('timestamp')
            .values('timestamp')[:1]
        )
        _rifle_returned_ts = (
            Transaction.objects
            .filter(
                transaction_type='Return',
                personnel=OuterRef('personnel'),
                rifle_id=OuterRef('rifle_id'),
                timestamp__gt=OuterRef('timestamp'),
            )
            .order_by('timestamp')
            .values('timestamp')[:1]
        )
        qs = (
            Transaction.objects
            .select_related('personnel', 'pistol', 'rifle')
            .annotate(
                effective_issuance=Coalesce('issuance_type', Subquery(_prior_withdrawal_issuance)),
                # due_by: for Withdrawals use their own return_by; for Returns use
                # the linked Withdrawal's return_by so the deadline is always the
                # original one, not a wrongly-propagated copy.
                due_by=Case(
                    When(transaction_type='Return', then=Subquery(_withdrawal_return_by)),
                    default=F('return_by'),
                ),
                # returned_at: for Withdrawal rows, the timestamp of the matching Return.
                returned_at=Coalesce(
                    Subquery(_pistol_returned_ts),
                    Subquery(_rifle_returned_ts),
                ),
            )
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


class TransactionDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Transaction
    template_name = 'transactions/transaction_detail.html'
    context_object_name = 'transaction'
    pk_url_kwarg = 'transaction_id'

    def test_func(self):
        return _can_view_transactions(self.request.user)

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
        # For Withdrawal rows: check if a matching Return exists so we can
        # suppress the OVERDUE badge when the item has already been returned.
        if transaction.transaction_type == 'Withdrawal':
            from django.db.models import Q as _Q
            _ret_filter = _Q()
            if transaction.pistol_id:
                _ret_filter |= _Q(pistol_id=transaction.pistol_id)
            if transaction.rifle_id:
                _ret_filter |= _Q(rifle_id=transaction.rifle_id)
            if _ret_filter:
                ctx['transaction_returned_at'] = (
                    Transaction.objects
                    .filter(
                        transaction_type='Return',
                        personnel=transaction.personnel,
                        timestamp__gt=transaction.timestamp,
                    )
                    .filter(_ret_filter)
                    .order_by('timestamp')
                    .values_list('timestamp', flat=True)
                    .first()
                )
            else:
                # Accessories-only withdrawal: look up any matching Return for
                # this personnel after this timestamp so OVERDUE is not shown
                # perpetually once the accessories have been returned.
                ctx['transaction_returned_at'] = (
                    Transaction.objects
                    .filter(
                        transaction_type='Return',
                        personnel=transaction.personnel,
                        timestamp__gt=transaction.timestamp,
                    )
                    .order_by('timestamp')
                    .values_list('timestamp', flat=True)
                    .first()
                )
        return ctx


@login_required
def create_transaction(request):
    if not _can_create_transaction(request.user):
        return HttpResponseForbidden("You do not have permission to create transactions.")
    from armguard.apps.users.models import SystemSettings
    _s = SystemSettings.get()
    _purpose_config = json.dumps({
        'Duty Sentinel': {
            'pistol': _s.purpose_duty_sentinel_show_pistol,  'rifle': _s.purpose_duty_sentinel_show_rifle,
            'holster_qty': _s.duty_sentinel_holster_qty, 'mag_pouch_qty': _s.duty_sentinel_mag_pouch_qty,
            'rifle_sling_qty': _s.duty_sentinel_rifle_sling_qty, 'bandoleer_qty': _s.duty_sentinel_bandoleer_qty,
            'rifle_short_mag_qty': _s.duty_sentinel_rifle_short_mag_qty, 'rifle_long_mag_qty': _s.duty_sentinel_rifle_long_mag_qty,
        },
        'Duty Vigil': {
            'pistol': _s.purpose_duty_vigil_show_pistol,     'rifle': _s.purpose_duty_vigil_show_rifle,
            'holster_qty': _s.duty_vigil_holster_qty, 'mag_pouch_qty': _s.duty_vigil_mag_pouch_qty,
            'rifle_sling_qty': _s.duty_vigil_rifle_sling_qty, 'bandoleer_qty': _s.duty_vigil_bandoleer_qty,
            'rifle_short_mag_qty': _s.duty_vigil_rifle_short_mag_qty, 'rifle_long_mag_qty': _s.duty_vigil_rifle_long_mag_qty,
        },
        'Duty Security': {
            'pistol': _s.purpose_duty_security_show_pistol,  'rifle': _s.purpose_duty_security_show_rifle,
            'holster_qty': _s.duty_security_holster_qty, 'mag_pouch_qty': _s.duty_security_mag_pouch_qty,
            'rifle_sling_qty': _s.duty_security_rifle_sling_qty, 'bandoleer_qty': _s.duty_security_bandoleer_qty,
            'rifle_short_mag_qty': _s.duty_security_rifle_short_mag_qty, 'rifle_long_mag_qty': _s.duty_security_rifle_long_mag_qty,
        },
        'Honor Guard': {
            'pistol': _s.purpose_honor_guard_show_pistol,    'rifle': _s.purpose_honor_guard_show_rifle,
            'holster_qty': _s.honor_guard_holster_qty, 'mag_pouch_qty': _s.honor_guard_mag_pouch_qty,
            'rifle_sling_qty': _s.honor_guard_rifle_sling_qty, 'bandoleer_qty': _s.honor_guard_bandoleer_qty,
            'rifle_short_mag_qty': _s.honor_guard_rifle_short_mag_qty, 'rifle_long_mag_qty': _s.honor_guard_rifle_long_mag_qty,
        },
        'Others': {
            'pistol': _s.purpose_others_show_pistol,         'rifle': _s.purpose_others_show_rifle,
            'holster_qty': _s.others_holster_qty, 'mag_pouch_qty': _s.others_mag_pouch_qty,
            'rifle_sling_qty': _s.others_rifle_sling_qty, 'bandoleer_qty': _s.others_bandoleer_qty,
            'rifle_short_mag_qty': _s.others_rifle_short_mag_qty, 'rifle_long_mag_qty': _s.others_rifle_long_mag_qty,
        },
        'OREX': {
            'pistol': _s.purpose_orex_show_pistol,           'rifle': _s.purpose_orex_show_rifle,
            'holster_qty': _s.orex_holster_qty, 'mag_pouch_qty': _s.orex_mag_pouch_qty,
            'rifle_sling_qty': _s.orex_rifle_sling_qty, 'bandoleer_qty': _s.orex_bandoleer_qty,
            'rifle_short_mag_qty': _s.orex_rifle_short_mag_qty, 'rifle_long_mag_qty': _s.orex_rifle_long_mag_qty,
        },
    })
    _txn_context = {
        'purpose_config':          _purpose_config,
        'tr_default_return_hours': _s.tr_default_return_hours,
        'default_issuance_type':   _s.default_issuance_type,
    }
    if request.method == 'POST':
        form = WithdrawalReturnTransactionForm(request.POST, request.FILES)
        try:
            _form_ok = form.is_valid()
        except Exception as _exc:
            _logger.exception('create_transaction: unexpected exception during form validation: %s', _exc)
            form.add_error(None, f'Form validation failed unexpectedly [{type(_exc).__name__}: {_exc}]. Please try again.')
            _form_ok = False
        if _form_ok:
            txn = form.save(commit=False)
            txn.transaction_personnel = request.user.get_full_name() or request.user.username
            try:
                txn.save(user=request.user)
            except ValidationError as ve:
                # Catch model-level binding/business rule errors and show them as form errors
                err_msgs = ve.messages if hasattr(ve, 'messages') else [str(ve)]
                for msg in err_msgs:
                    form.add_error(None, msg)
                return render(request, 'transactions/transaction_form.html', {**_txn_context, 'form': form})
            # Invalidate dashboard caches so counts and table reflect the new transaction immediately.
            from django.utils import timezone as _tz
            cache.delete(f'dashboard_stats_{_tz.localdate()}')
            cache.delete('dashboard_inventory_tables')

            # Create discrepancy record if the operator flagged one on Return.
            if (request.POST.get('report_discrepancy')
                    and txn.transaction_type == 'Return'):
                from armguard.apps.inventory.pistol_rifle_discrepancy_model import FirearmDiscrepancy
                _disc_type = request.POST.get('discrepancy_type', '').strip()
                _disc_desc = request.POST.get('discrepancy_description', '').strip()
                if _disc_type and _disc_desc:
                    # Create one record per firearm involved in this return.
                    _firearms = []
                    if txn.pistol_id:
                        _firearms.append({'pistol_id': txn.pistol_id, 'rifle_id': None})
                    if txn.rifle_id:
                        _firearms.append({'pistol_id': None, 'rifle_id': txn.rifle_id})
                    for _fw in _firearms:
                        try:
                            _disc_image   = _validate_discrepancy_image(request.FILES.get('discrepancy_image'))
                            _disc_image_2 = _validate_discrepancy_image(request.FILES.get('discrepancy_image_2'))
                            _disc_image_3 = _validate_discrepancy_image(request.FILES.get('discrepancy_image_3'))
                            _disc_image_4 = _validate_discrepancy_image(request.FILES.get('discrepancy_image_4'))
                            _disc_image_5 = _validate_discrepancy_image(request.FILES.get('discrepancy_image_5'))
                            FirearmDiscrepancy.objects.create(
                                pistol_id=_fw['pistol_id'],
                                rifle_id=_fw['rifle_id'],
                                withdrawer=txn.personnel,
                                related_transaction=txn,
                                discrepancy_type=_disc_type,
                                description=_disc_desc,
                                image=_disc_image,
                                image_2=_disc_image_2,
                                image_3=_disc_image_3,
                                image_4=_disc_image_4,
                                image_5=_disc_image_5,
                                status='Open',
                                reported_by=request.user,
                            )
                        except Exception as _disc_exc:
                            import logging as _log_mod
                            _log_mod.getLogger(__name__).exception(
                                'Discrepancy creation failed for transaction #%s: %s',
                                txn.transaction_id, _disc_exc,
                            )  # Error must never block the Return

            messages.success(request, f'Transaction #{txn.transaction_id} recorded successfully.')
            # Auto-print: if the per-purpose setting is enabled and this is a TR Withdrawal,
            # redirect straight to the print page instead of the detail page.
            try:
                from armguard.apps.users.models import SystemSettings as _SS_print
                _ss_print = _SS_print.get()
                _purpose_auto_map = {
                    'Duty Sentinel': 'auto_print_tr_duty_sentinel',
                    'Duty Vigil':    'auto_print_tr_duty_vigil',
                    'Duty Security': 'auto_print_tr_duty_security',
                    'Honor Guard':   'auto_print_tr_honor_guard',
                    'Others':        'auto_print_tr_others',
                    'OREX':          'auto_print_tr_orex',
                }
                _auto_field = _purpose_auto_map.get(txn.purpose, '')
                _auto = bool(_auto_field and getattr(_ss_print, _auto_field, False))
            except Exception:
                _auto = False
            if (_auto
                    and txn.transaction_type == 'Withdrawal'
                    and txn.issuance_type
                    and 'TR' in txn.issuance_type):
                from django.urls import reverse
                return redirect(reverse('print_handler:print_transaction_pdf',
                                        kwargs={'transaction_id': txn.transaction_id}))
            return redirect('transaction-detail', transaction_id=txn.transaction_id)
    else:
        form = WithdrawalReturnTransactionForm()
    return render(request, 'transactions/transaction_form.html', {**_txn_context, 'form': form})


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
    import logging
    import datetime as _dt
    from types import SimpleNamespace
    from django.utils import timezone
    from armguard.apps.print.pdf_filler.form_filler import TransactionFormFiller
    from armguard.apps.users.models import SystemSettings

    _log = logging.getLogger(__name__)

    # ── Step 1: form validation ───────────────────────────────────────────────
    # Wrap is_valid() separately so an unexpected exception inside _post_clean()
    # (e.g. Transaction.clean() raising a non-ValidationError) still returns JSON
    # instead of a raw HTML 500 page.
    form = WithdrawalReturnTransactionForm(request.POST, request.FILES)
    try:
        _form_valid = form.is_valid()
    except Exception as exc:
        _log.exception('TR preview: unexpected exception during form validation: %s', exc)
        _err_msg = f'Form validation failed unexpectedly [{type(exc).__name__}: {exc}]. Please try again.'
        return JsonResponse(
            {'field_errors': {}, 'non_field_errors': [_err_msg]},
            status=400,
        )

    if not _form_valid:
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

    # ── Step 2: build mock_txn and generate PDF ───────────────────────────────
    # Everything from cleaned-data extraction through PDF generation is inside
    # one broad try so that any unexpected exception produces a clean JSON
    # response rather than an HTML 500 page.
    try:
        cd = form.cleaned_data
        personnel = cd['personnel']
        pistol     = cd.get('pistol')
        rifle      = cd.get('rifle')
        purpose    = cd.get('purpose') or ''

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

        try:
            _default_hours = int(SystemSettings.get().tr_default_return_hours or 24)
        except Exception:
            _default_hours = 24
        _default_return_by = timezone.now() + _dt.timedelta(hours=_default_hours)

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
            return_by=cd.get('return_by') or _default_return_by,
        )

        filler = TransactionFormFiller()
        pdf_bytes = filler.fill_transaction_form(mock_txn)
        pdf_data  = pdf_bytes.read()

    except Exception as exc:
        _log.exception('TR preview: failed during PDF generation: %s', exc)
        return JsonResponse(
            {'field_errors': {}, 'non_field_errors': ['Preview generation failed. Please try again.']},
            status=400,
        )

    from utils.pdf_viewer import serve_pdf_bytes
    return serve_pdf_bytes(
        request,
        pdf_bytes=pdf_data,
        filename='TR_Preview.pdf',
        label='TR Preview (in-progress transaction)',
    )


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
    # For Return form auto-fill: resolve open TransactionLog to get actual FKs
    # (Personnel stores magazine/ammo as strings, not PKs — we need PKs for dropdowns)
    _open_log = (
        TransactionLogs.objects
        .filter(personnel_id=p, log_status__in=['Open', 'Partially Returned'])
        .order_by('-record_id')
        .first()
    )
    if _open_log:
        data['open_rifle_mag_id']   = _open_log.withdraw_rifle_magazine_id
        data['open_pistol_mag_id']  = _open_log.withdraw_pistol_magazine_id
        data['open_pistol_ammo_id'] = _open_log.withdraw_pistol_ammunition_id
        data['open_rifle_ammo_id']  = _open_log.withdraw_rifle_ammunition_id
    else:
        data['open_rifle_mag_id'] = data['open_pistol_mag_id'] = None
        data['open_pistol_ammo_id'] = data['open_rifle_ammo_id'] = None
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
@ratelimit(rate='30/m')
def personnel_search(request):
    """
    Typeahead search: match personnel by first_name, last_name, or AFSN.
    GET ?q=<text>  — returns up to 10 results.
    """
    from armguard.apps.personnel.models import Personnel
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})
    qs = Personnel.objects.filter(
        Q(first_name__icontains=q) |
        Q(last_name__icontains=q) |
        Q(AFSN__icontains=q)
    ).order_by('last_name', 'first_name')[:10]
    results = [
        {
            'id': p.Personnel_ID,
            'rank': p.rank or '',
            'first_name': p.first_name,
            'last_name': p.last_name,
            'AFSN': p.AFSN or '',
        }
        for p in qs
    ]
    return JsonResponse({'results': results})


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
        'has_open_discrepancy': not ok and reason and 'open discrepancy' in reason.lower(),
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
