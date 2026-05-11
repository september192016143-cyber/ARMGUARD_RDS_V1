from django import forms
from .models import Transaction, TransactionLogs, PURPOSE_CHOICES
from armguard.apps.inventory.models import Pistol, Rifle

class TransactionAdminForm(forms.ModelForm):
    # Explicit purpose field: renders a dropdown in admin but accepts any string value
    # (including custom 'Others' text). Choices are UI helpers only — not model-level constraints.
    purpose = forms.CharField(
        required=True,
        label="Purpose",
        widget=forms.Select(choices=PURPOSE_CHOICES),
    )
    par_document = forms.FileField(
        required=False,
        label="PAR Document (PDF)",
        help_text="Required when Issuance Type is PAR. Will be saved as PAR_rank_lastname_transactionID.pdf."
    )
    qr_item_id = forms.CharField(
        label="QR/Item ID Scan",
        required=False,
        help_text="Scan or enter the item ID/QR code to auto-select the item."
    )
    qr_personnel_id = forms.CharField(
        label="QR/Personnel ID Scan",
        required=False,
        help_text="Scan or enter the Personnel ID/QR code to auto-select personnel."
    )
    # Accessory checkboxes — checking one auto-assigns the pool and standard qty.
    include_pistol_holster = forms.BooleanField(
        required=False, label="Pistol Holster",
        help_text="Standard issue: 1 unit."
    )
    include_magazine_pouch = forms.BooleanField(
        required=False, label="Magazine Pouch",
        help_text="Standard issue: up to 3 units."
    )
    include_rifle_sling = forms.BooleanField(
        required=False, label="Rifle Sling",
        help_text="Standard issue: 1 unit."
    )
    include_bandoleer = forms.BooleanField(
        required=False, label="Bandoleer",
        help_text="Standard issue: 1 unit."
    )

    class Meta:
        model = Transaction
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        qr_item_id = cleaned_data.get('qr_item_id')
        errors = []
        if qr_item_id:
            try:
                pistol = Pistol.objects.get(item_id=qr_item_id)
                cleaned_data['pistol'] = pistol
                cleaned_data['rifle'] = None
            except Pistol.DoesNotExist:
                try:
                    rifle = Rifle.objects.get(item_id=qr_item_id)
                    cleaned_data['rifle'] = rifle
                    cleaned_data['pistol'] = None
                except Rifle.DoesNotExist:
                    self.add_error('qr_item_id', f'No item found matching scanned ID "{qr_item_id}".')
        qr_personnel_id = cleaned_data.get('qr_personnel_id')
        if qr_personnel_id:
            try:
                from armguard.apps.personnel.models import Personnel
                person = Personnel.objects.get(Personnel_ID=qr_personnel_id)
                cleaned_data['personnel'] = person
            except Personnel.DoesNotExist:
                self.add_error('qr_personnel_id', f'No personnel found with ID "{qr_personnel_id}".')
        if not cleaned_data.get('personnel'):
            errors.append('Personnel is required for every transaction.')

        transaction_type = cleaned_data.get('transaction_type')
        pistol = cleaned_data.get('pistol')
        rifle = cleaned_data.get('rifle')
        pistol_holster_quantity = cleaned_data.get('pistol_holster_quantity')
        magazine_pouch_quantity = cleaned_data.get('magazine_pouch_quantity')
        rifle_sling_quantity = cleaned_data.get('rifle_sling_quantity')
        bandoleer_quantity = cleaned_data.get('bandoleer_quantity')
        pistol_magazine = cleaned_data.get('pistol_magazine')
        pistol_magazine_quantity = cleaned_data.get('pistol_magazine_quantity')
        rifle_magazine = cleaned_data.get('rifle_magazine')
        rifle_magazine_quantity = cleaned_data.get('rifle_magazine_quantity')
        pistol_ammunition = cleaned_data.get('pistol_ammunition')
        pistol_ammunition_quantity = cleaned_data.get('pistol_ammunition_quantity')
        rifle_ammunition = cleaned_data.get('rifle_ammunition')
        rifle_ammunition_quantity = cleaned_data.get('rifle_ammunition_quantity')
        personnel = cleaned_data.get('personnel')

        # ── AUTO-FILL: Duty Sentinel + Glock 17 9mm ──────────────────────────────
        # When a Withdrawal is being processed for a Glock 17 9mm under Duty Sentinel,
        # automatically populate the standard loadout if the user left those fields blank.
        # Note: if the Pistol visibility column is disabled via SystemSettings for Duty
        # Sentinel, the JS hides the pistol field and it will not be submitted, so
        # `pistol` will be None here and this block will not fire — safe by design.
        purpose_val = cleaned_data.get('purpose')
        from armguard.apps.users.models import SystemSettings as _SS
        try:
            _s = _SS.get()
        except Exception as _ss_exc:
            raise forms.ValidationError(
                'System settings are unavailable — ensure all database migrations have been applied.'
            ) from _ss_exc
        if (
            transaction_type == 'Withdrawal'
            and purpose_val == 'Duty Sentinel'
            and pistol
            and getattr(pistol, 'model', None) == 'Glock 17 9mm'
            and (_s.purpose_duty_sentinel_auto_accessories or _s.purpose_duty_sentinel_auto_consumables)
        ):
            from armguard.apps.inventory.models import Magazine, Ammunition
            if _s.purpose_duty_sentinel_auto_accessories:
                # Pistol Holster
                if not pistol_holster_quantity and _s.duty_sentinel_holster_qty > 0:
                    cleaned_data['pistol_holster_quantity'] = _s.duty_sentinel_holster_qty
                    pistol_holster_quantity = _s.duty_sentinel_holster_qty
                    cleaned_data['include_pistol_holster'] = True
                # Magazine Pouch
                if not magazine_pouch_quantity and _s.duty_sentinel_mag_pouch_qty > 0:
                    cleaned_data['magazine_pouch_quantity'] = _s.duty_sentinel_mag_pouch_qty
                    magazine_pouch_quantity = _s.duty_sentinel_mag_pouch_qty
                    cleaned_data['include_magazine_pouch'] = True
            if _s.purpose_duty_sentinel_auto_consumables:
                # Pistol Magazine — Duty Sentinel is always Glock 17 9mm (outer guard)
                if not pistol_magazine:
                    mag_pool = Magazine.objects.filter(type='Mag Assy, 9mm: Glock 17').order_by('-quantity').first()
                    if mag_pool:
                        cleaned_data['pistol_magazine'] = mag_pool
                        pistol_magazine = mag_pool
                if not pistol_magazine_quantity and _s.duty_sentinel_pistol_mag_qty > 0:
                    cleaned_data['pistol_magazine_quantity'] = _s.duty_sentinel_pistol_mag_qty
                    pistol_magazine_quantity = _s.duty_sentinel_pistol_mag_qty
                # Pistol Ammunition — M882
                if not pistol_ammunition:
                    ammo_pool = Ammunition.objects.filter(type='M882 9x19mm Ball 435 Ctg').first()
                    if ammo_pool:
                        cleaned_data['pistol_ammunition'] = ammo_pool
                        pistol_ammunition = ammo_pool
                if not pistol_ammunition_quantity and _s.duty_sentinel_pistol_ammo_qty > 0:
                    cleaned_data['pistol_ammunition_quantity'] = _s.duty_sentinel_pistol_ammo_qty
                    pistol_ammunition_quantity = _s.duty_sentinel_pistol_ammo_qty
        # ── AUTO-FILL: Duty Security + Rifle ─────────────────────────────────────
        # When a Withdrawal is processed for any Rifle under Duty Security,
        # automatically populate the standard loadout if the user left those fields blank.
        if (
            transaction_type == 'Withdrawal'
            and purpose_val == 'Duty Security'
            and rifle
            and (_s.purpose_duty_security_auto_accessories or _s.purpose_duty_security_auto_consumables)
        ):
            from armguard.apps.inventory.models import Magazine, Ammunition
            if _s.purpose_duty_security_auto_accessories:
                # Rifle Sling — standard issue for Duty Security
                if not rifle_sling_quantity and _s.duty_security_rifle_sling_qty > 0:
                    cleaned_data['rifle_sling_quantity'] = _s.duty_security_rifle_sling_qty
                    rifle_sling_quantity = _s.duty_security_rifle_sling_qty
                    cleaned_data['include_rifle_sling'] = True
            if _s.purpose_duty_security_auto_consumables:
                # Rifle Magazine — caliber-aware:
                #   M14 7.62mm   → 'M14' capacity pool
                #   EMTAN 5.56mm → 'EMTAN' capacity (30-rounds EMTAN-specific mag)
                #   Other 5.56mm → generic '30-rounds' alloy pool
                if not rifle_magazine:
                    _ds_rifle_model = getattr(rifle, 'model', '') if rifle else ''
                    if _ds_rifle_model == 'M14 Rifle 7.62mm':
                        mag_pool = Magazine.objects.filter(weapon_type='Rifle', capacity='M14').order_by('-quantity').first()
                    elif _ds_rifle_model == 'M4 14.5" DGIS EMTAN 5.56mm':
                        mag_pool = Magazine.objects.filter(weapon_type='Rifle', type='Mag Assy, 5.56mm: EMTAN').order_by('-quantity').first()
                    else:
                        mag_pool = Magazine.objects.filter(weapon_type='Rifle', capacity='30-rounds').order_by('-quantity').first()
                    if mag_pool:
                        cleaned_data['rifle_magazine'] = mag_pool
                        rifle_magazine = mag_pool
                if not rifle_magazine_quantity:
                    _long_qty = _s.duty_security_rifle_long_mag_qty
                    if _long_qty > 0:
                        cleaned_data['rifle_magazine_quantity'] = _long_qty
                        rifle_magazine_quantity = _long_qty
                # Rifle Ammunition — caliber-aware: use AMMO_WEAPON_COMPATIBILITY to match the issued rifle.
                if not rifle_ammunition:
                    from armguard.apps.inventory.models import AMMO_WEAPON_COMPATIBILITY
                    _ds_rifle_model = getattr(rifle, 'model', '') if rifle else ''
                    for _ammo_type, _weapons in AMMO_WEAPON_COMPATIBILITY.items():
                        if _ds_rifle_model in _weapons:
                            ammo_pool = Ammunition.objects.filter(type=_ammo_type).first()
                            if ammo_pool:
                                cleaned_data['rifle_ammunition'] = ammo_pool
                                rifle_ammunition = ammo_pool
                            break
                if not rifle_ammunition_quantity and _s.duty_security_rifle_ammo_qty > 0:
                    cleaned_data['rifle_ammunition_quantity'] = _s.duty_security_rifle_ammo_qty
                    rifle_ammunition_quantity = _s.duty_security_rifle_ammo_qty
        # ── AUTO-ASSIGN: Pistol magazine pool whenever quantity is given ──────────
        # All 6 purposes are now independently configurable for auto-consumables.
        # NOTE: all blocks below are Withdrawal-only; the transaction_type guard is
        # applied individually so Returns never receive auto-filled FKs or quantities.
        _purpose_consumables_map = {
            'Duty Sentinel': _s.purpose_duty_sentinel_auto_consumables,
            'Duty Vigil':    _s.purpose_duty_vigil_auto_consumables,
            'Duty Security': _s.purpose_duty_security_auto_consumables,
            'Honor Guard':   _s.purpose_honor_guard_auto_consumables,
            'Others':        _s.purpose_others_auto_consumables,
            'OREX':          _s.purpose_orex_auto_consumables,
        }
        _no_auto_consumables = not bool(_purpose_consumables_map.get(purpose_val, False))
        # Per-purpose loadout quantity helper
        _purpose_prefix_map = {
            'Duty Sentinel': 'duty_sentinel',
            'Duty Vigil':    'duty_vigil',
            'Duty Security': 'duty_security',
            'Honor Guard':   'honor_guard',
            'Others':        'others',
            'OREX':          'orex',
        }
        _pfx = _purpose_prefix_map.get(purpose_val, '')
        def _lq(field_suffix, fallback=0):
            if _pfx:
                val = getattr(_s, f'{_pfx}_{field_suffix}', fallback)
                return int(val) if val is not None else fallback
            return fallback
        if transaction_type == 'Withdrawal' and not _no_auto_consumables and pistol_magazine_quantity and not pistol_magazine:
            from armguard.apps.inventory.models import Magazine, MAG_WEAPON_COMPATIBILITY
            _pa_pistol_model = getattr(pistol, 'model', '') if pistol else ''
            _pa_allowed_types = [t for t, models in MAG_WEAPON_COMPATIBILITY.items() if _pa_pistol_model in models]
            if _pa_allowed_types:
                mag_pool = Magazine.objects.filter(weapon_type='Pistol', type__in=_pa_allowed_types).order_by('-quantity').first()
            else:
                mag_pool = Magazine.objects.filter(weapon_type='Pistol').order_by('-quantity').first()
            if mag_pool:
                cleaned_data['pistol_magazine'] = mag_pool
                pistol_magazine = mag_pool
        # ── AUTO-ASSIGN: Rifle magazine pool when qty is given but no magazine selected ──
        # Covers the case where the JS pre-fills the quantity field before the user picks a
        # magazine from the dropdown — qty arrives but FK is still blank.
        # Withdrawal-only: a Return operator must explicitly select the magazine FK so the
        # open-log lookup in update_return_logs() matches the correct withdrawn record.
        if transaction_type == 'Withdrawal' and rifle_magazine_quantity and not rifle_magazine:
            from armguard.apps.inventory.models import Magazine
            _ar_rifle_model = getattr(rifle, 'model', '') if rifle else ''
            if _ar_rifle_model == 'M14 Rifle 7.62mm':
                _ar_default_cap = 'M14'
                mag_pool = Magazine.objects.filter(weapon_type='Rifle', capacity=_ar_default_cap).order_by('-quantity').first()
            elif _ar_rifle_model == 'M4 14.5" DGIS EMTAN 5.56mm':
                mag_pool = Magazine.objects.filter(weapon_type='Rifle', type='Mag Assy, 5.56mm: EMTAN').order_by('-quantity').first()
            else:
                mag_pool = Magazine.objects.filter(weapon_type='Rifle', capacity='20-rounds').order_by('-quantity').first()
            if mag_pool:
                cleaned_data['rifle_magazine'] = mag_pool
                rifle_magazine = mag_pool
        # ── AUTO-FILL: Pistol magazine quantity when blank ────────────────────────
        if transaction_type == 'Withdrawal' and not _no_auto_consumables and pistol and not pistol_magazine_quantity and _lq('pistol_mag_qty') > 0:
            cleaned_data['pistol_magazine_quantity'] = _lq('pistol_mag_qty')
            pistol_magazine_quantity = _lq('pistol_mag_qty')
            if not pistol_magazine:
                from armguard.apps.inventory.models import Magazine, MAG_WEAPON_COMPATIBILITY
                _pf_pistol_model = getattr(pistol, 'model', '')
                _pf_allowed_types = [t for t, models in MAG_WEAPON_COMPATIBILITY.items() if _pf_pistol_model in models]
                if _pf_allowed_types:
                    mag_pool = Magazine.objects.filter(weapon_type='Pistol', type__in=_pf_allowed_types).order_by('-quantity').first()
                else:
                    mag_pool = Magazine.objects.filter(weapon_type='Pistol').order_by('-quantity').first()
                if mag_pool:
                    cleaned_data['pistol_magazine'] = mag_pool
                    pistol_magazine = mag_pool
        # ── AUTO-FILL: Rifle magazine quantity when blank ─────────────────────────
        if transaction_type == 'Withdrawal' and not _no_auto_consumables and rifle and not rifle_magazine_quantity:
            _rm_cap = getattr(cleaned_data.get('rifle_magazine'), 'capacity', None)
            _af_rifle_model = getattr(rifle, 'model', '')
            if _af_rifle_model == 'M14 Rifle 7.62mm':
                # M14 is a 7.62mm rifle — use short-mag qty slot as no dedicated M14 setting exists
                _rm_qty = _lq('rifle_short_mag_qty')
            elif _af_rifle_model == 'M4 14.5" DGIS EMTAN 5.56mm':
                # EMTAN rifle uses its own EMTAN mag; treat as 30-round equivalent for qty purposes
                _rm_qty = _lq('rifle_long_mag_qty')
            else:
                _rm_qty = _lq('rifle_long_mag_qty') if _rm_cap == '30-rounds' else _lq('rifle_short_mag_qty')
            if _rm_qty > 0:
                cleaned_data['rifle_magazine_quantity'] = _rm_qty
                rifle_magazine_quantity = _rm_qty
                if not cleaned_data.get('rifle_magazine'):
                    from armguard.apps.inventory.models import Magazine
                    if _af_rifle_model == 'M14 Rifle 7.62mm':
                        _preferred_cap = 'M14'
                        mag_pool = Magazine.objects.filter(weapon_type='Rifle', capacity=_preferred_cap).order_by('-quantity').first()
                    elif _af_rifle_model == 'M4 14.5" DGIS EMTAN 5.56mm':
                        mag_pool = Magazine.objects.filter(weapon_type='Rifle', type='Mag Assy, 5.56mm: EMTAN').order_by('-quantity').first()
                    else:
                        _preferred_cap = _rm_cap or '20-rounds'
                        mag_pool = Magazine.objects.filter(weapon_type='Rifle', capacity=_preferred_cap).order_by('-quantity').first()
                    if mag_pool:
                        cleaned_data['rifle_magazine'] = mag_pool
                        rifle_magazine = mag_pool
        # ── AUTO-ASSIGN: Ammunition pool based on selected weapon model ──────────
        # Only auto-assign the ammo FK when the purpose's configured ammo qty > 0.
        # If the admin set e.g. orex_rifle_ammo_qty = 0, no ammo should be issued
        # for that purpose, so don't pre-select an ammo pool at all.
        from armguard.apps.inventory.models import Ammunition, AMMO_WEAPON_COMPATIBILITY
        if transaction_type == 'Withdrawal' and not _no_auto_consumables and pistol and not pistol_ammunition and _lq('pistol_ammo_qty') > 0:
            pistol_model = getattr(pistol, 'model', '')
            for ammo_type, weapons in AMMO_WEAPON_COMPATIBILITY.items():
                if pistol_model in weapons:
                    # B-3 FIX: order by -quantity so the most-stocked pool is selected,
                    # matching the ordering used for magazine and accessory auto-fill.
                    ammo_pool = Ammunition.objects.filter(type=ammo_type).order_by('-quantity').first()
                    if ammo_pool:
                        cleaned_data['pistol_ammunition'] = ammo_pool
                        pistol_ammunition = ammo_pool
                    break
        if transaction_type == 'Withdrawal' and not _no_auto_consumables and rifle and not rifle_ammunition and _lq('rifle_ammo_qty') > 0:
            rifle_model = getattr(rifle, 'model', '')
            for ammo_type, weapons in AMMO_WEAPON_COMPATIBILITY.items():
                if rifle_model in weapons:
                    # B-3 FIX: order by -quantity so the most-stocked pool is selected.
                    ammo_pool = Ammunition.objects.filter(type=ammo_type).order_by('-quantity').first()
                    if ammo_pool:
                        cleaned_data['rifle_ammunition'] = ammo_pool
                        rifle_ammunition = ammo_pool
                    break
        # ── AUTO-FILL: Ammo quantities when blank ─────────────────────────────────
        if transaction_type == 'Withdrawal' and not _no_auto_consumables and pistol and not pistol_ammunition_quantity and _lq('pistol_ammo_qty') > 0:
            cleaned_data['pistol_ammunition_quantity'] = _lq('pistol_ammo_qty')
            pistol_ammunition_quantity = _lq('pistol_ammo_qty')
        if transaction_type == 'Withdrawal' and not _no_auto_consumables and rifle and not rifle_ammunition_quantity and _lq('rifle_ammo_qty') > 0:
            cleaned_data['rifle_ammunition_quantity'] = _lq('rifle_ammo_qty')
            rifle_ammunition_quantity = _lq('rifle_ammo_qty')
        # ── AUTO-ASSIGN: Accessories ──────────────────────────────────────────────
        # If auto_accessories is True for this purpose, auto-flag the standard
        # accessories for the weapon type (pistol → holster + mag pouch; rifle → sling).
        _purpose_accessories_map = {
            'Duty Sentinel': _s.purpose_duty_sentinel_auto_accessories,
            'Duty Vigil':    _s.purpose_duty_vigil_auto_accessories,
            'Duty Security': _s.purpose_duty_security_auto_accessories,
            'Honor Guard':   _s.purpose_honor_guard_auto_accessories,
            'Others':        _s.purpose_others_auto_accessories,
            'OREX':          _s.purpose_orex_auto_accessories,
        }
        _auto_accessories = bool(_purpose_accessories_map.get(purpose_val, False))
        if transaction_type == 'Withdrawal' and _auto_accessories:
            if pistol and not pistol_holster_quantity and _lq('holster_qty') > 0:
                cleaned_data['include_pistol_holster'] = True
            if (pistol or rifle) and not magazine_pouch_quantity and _lq('mag_pouch_qty') > 0:
                cleaned_data['include_magazine_pouch'] = True
            if rifle and not rifle_sling_quantity and _lq('rifle_sling_qty') > 0:
                cleaned_data['include_rifle_sling'] = True
        # Apply standard quantities for all checked or auto-flagged accessories
        # (Withdrawal-only: on Returns the user explicitly states what they're returning)
        if transaction_type == 'Withdrawal' and cleaned_data.get('include_pistol_holster') and not pistol_holster_quantity:
            _qty = _lq('holster_qty')
            if _qty > 0:
                cleaned_data['pistol_holster_quantity'] = _qty
                pistol_holster_quantity = _qty
        if transaction_type == 'Withdrawal' and cleaned_data.get('include_magazine_pouch') and not magazine_pouch_quantity:
            _qty = _lq('mag_pouch_qty')
            if _qty > 0:
                cleaned_data['magazine_pouch_quantity'] = _qty
                magazine_pouch_quantity = _qty
        if transaction_type == 'Withdrawal' and cleaned_data.get('include_rifle_sling') and not rifle_sling_quantity:
            _qty = _lq('rifle_sling_qty')
            if _qty > 0:
                cleaned_data['rifle_sling_quantity'] = _qty
                rifle_sling_quantity = _qty
        if transaction_type == 'Withdrawal' and cleaned_data.get('include_bandoleer') and not bandoleer_quantity:
            _qty = _lq('bandoleer_qty')
            if _qty > 0:
                cleaned_data['bandoleer_quantity'] = _qty
                bandoleer_quantity = _qty
        # ── END AUTO-FILL ─────────────────────────────────────────────────────────

        # ── RETURN: resolve include_* checkboxes → quantities from the open withdrawal log ──
        # The template renders accessories as checkboxes (include_pistol_holster, etc.)
        # rather than numeric input fields. When a checkbox is checked on a Return,
        # we look up the open withdrawal log and use the originally-issued quantity
        # so that the binding-rule check below sees a non-zero value and does not
        # incorrectly report the item as missing.
        if transaction_type == 'Return':
            from .models import TransactionLogs as _TL_ret
            if pistol and personnel and (
                (cleaned_data.get('include_pistol_holster') and not pistol_holster_quantity)
                or (cleaned_data.get('include_magazine_pouch') and not magazine_pouch_quantity)
            ):
                _plog_ret = _TL_ret.objects.filter(
                    personnel_id=personnel,
                    withdraw_pistol=pistol,
                    return_pistol__isnull=True,
                    log_status__in=['Open', 'Partially Returned'],
                ).order_by('-withdraw_pistol_timestamp').first()
                if _plog_ret:
                    if cleaned_data.get('include_pistol_holster') and not pistol_holster_quantity and _plog_ret.withdraw_pistol_holster_quantity:
                        cleaned_data['pistol_holster_quantity'] = _plog_ret.withdraw_pistol_holster_quantity
                        pistol_holster_quantity = _plog_ret.withdraw_pistol_holster_quantity
                    if cleaned_data.get('include_magazine_pouch') and not magazine_pouch_quantity and _plog_ret.withdraw_magazine_pouch_quantity:
                        cleaned_data['magazine_pouch_quantity'] = _plog_ret.withdraw_magazine_pouch_quantity
                        magazine_pouch_quantity = _plog_ret.withdraw_magazine_pouch_quantity
            if rifle and personnel and (
                (cleaned_data.get('include_rifle_sling') and not rifle_sling_quantity)
                or (cleaned_data.get('include_bandoleer') and not bandoleer_quantity)
            ):
                _rlog_ret = _TL_ret.objects.filter(
                    personnel_id=personnel,
                    withdraw_rifle=rifle,
                    return_rifle__isnull=True,
                    log_status__in=['Open', 'Partially Returned'],
                ).order_by('-withdraw_rifle_timestamp').first()
                if _rlog_ret:
                    if cleaned_data.get('include_rifle_sling') and not rifle_sling_quantity and _rlog_ret.withdraw_rifle_sling_quantity:
                        cleaned_data['rifle_sling_quantity'] = _rlog_ret.withdraw_rifle_sling_quantity
                        rifle_sling_quantity = _rlog_ret.withdraw_rifle_sling_quantity
                    if cleaned_data.get('include_bandoleer') and not bandoleer_quantity and _rlog_ret.withdraw_bandoleer_quantity:
                        cleaned_data['bandoleer_quantity'] = _rlog_ret.withdraw_bandoleer_quantity
                        bandoleer_quantity = _rlog_ret.withdraw_bandoleer_quantity

        # At least one item must be present
        has_any = any([pistol, rifle, pistol_magazine, rifle_magazine, pistol_ammunition, rifle_ammunition, pistol_holster_quantity, magazine_pouch_quantity, rifle_sling_quantity, bandoleer_quantity])
        if not has_any:
            errors.append('At least one item (Pistol, Rifle, Magazine, Ammunition, or Accessory) must be selected.')

        # Withdrawal requires at least one firearm — accessories and consumables
        # alone cannot be the sole items on a Withdrawal transaction.
        if transaction_type == 'Withdrawal' and not pistol and not rifle:
            errors.append('A Withdrawal must include at least one firearm (Pistol or Rifle). Accessories and consumables cannot be withdrawn without a firearm.')

        if transaction_type == 'Withdrawal':
            if pistol:
                fresh_pistol = Pistol.objects.get(pk=pistol.pk)
                ok, reason = fresh_pistol.can_be_withdrawn()
                if not ok and reason not in errors:
                    errors.append(reason)
            if pistol and personnel and personnel.has_pistol_issued():
                msg = f"Personnel {personnel.Personnel_ID} already has a pistol issued: {personnel.pistol_item_issued}. Only one pistol can be issued at a time."
                if msg not in errors:
                    errors.append(msg)
            if rifle:
                fresh_rifle = Rifle.objects.get(pk=rifle.pk)
                ok, reason = fresh_rifle.can_be_withdrawn()
                if not ok and reason not in errors:
                    errors.append(reason)
            if rifle and personnel and personnel.has_rifle_issued():
                msg = f"Personnel {personnel.Personnel_ID} already has a rifle issued: {personnel.rifle_item_issued}. Only one rifle can be issued at a time."
                if msg not in errors:
                    errors.append(msg)
            # Pistol magazine quantity check
            if pistol_magazine:
                qty = pistol_magazine_quantity or 0
                if qty <= 0:
                    errors.append('Pistol magazine quantity must be greater than 0 for withdrawal.')
                else:
                    fresh = pistol_magazine.__class__.objects.get(pk=pistol_magazine.pk)
                    ok, reason = fresh.can_be_withdrawn(qty)
                    if not ok and reason not in errors:
                        errors.append(reason)
            # Rifle magazine quantity check
            if rifle_magazine:
                qty = rifle_magazine_quantity or 0
                if qty <= 0:
                    errors.append('Rifle magazine quantity must be greater than 0 for withdrawal.')
                else:
                    fresh = rifle_magazine.__class__.objects.get(pk=rifle_magazine.pk)
                    ok, reason = fresh.can_be_withdrawn(qty)
                    if not ok and reason not in errors:
                        errors.append(reason)
            # Pistol ammunition quantity check
            # The qty > 0 requirement is skipped when the purpose's configured
            # pistol_ammo_qty is 0 — meaning the admin opted out of ammo for this purpose.
            if pistol_ammunition:
                qty = pistol_ammunition_quantity or 0
                if qty <= 0 and _lq('pistol_ammo_qty') > 0:
                    errors.append('Pistol ammunition quantity must be greater than 0 for withdrawal.')
                elif qty > 0:
                    fresh = pistol_ammunition.__class__.objects.get(pk=pistol_ammunition.pk)
                    ok, reason = fresh.can_be_withdrawn(qty)
                    if not ok and reason not in errors:
                        errors.append(reason)
            # Rifle ammunition quantity check
            # Same logic: skip the qty > 0 requirement if the purpose allows zero ammo.
            if rifle_ammunition:
                qty = rifle_ammunition_quantity or 0
                if qty <= 0 and _lq('rifle_ammo_qty') > 0:
                    errors.append('Rifle ammunition quantity must be greater than 0 for withdrawal.')
                elif qty > 0:
                    fresh = rifle_ammunition.__class__.objects.get(pk=rifle_ammunition.pk)
                    ok, reason = fresh.can_be_withdrawn(qty)
                    if not ok and reason not in errors:
                        errors.append(reason)
            # Accessory quantity checks — each type validated independently by type lookup
            from armguard.apps.inventory.models import _get_accessory_max_qty, Accessory
            _live_acc_max = _get_accessory_max_qty()
            _form_accs = [
                (pistol_holster_quantity,  'Pistol Holster'),
                (magazine_pouch_quantity,  'Pistol Magazine Pouch'),
                (rifle_sling_quantity,     'Rifle Sling'),
                (bandoleer_quantity,       'Bandoleer'),
            ]
            for acc_qty, acc_label in _form_accs:
                if acc_qty:
                    # B-2 FIX: order by -quantity so validation checks the same pool that
                    # models.py clean() and services.adjust_consumable_quantities() use.
                    acc_pool = Accessory.objects.filter(type=acc_label).order_by('-quantity').first()
                    if acc_pool:
                        ok, reason = acc_pool.can_be_withdrawn(acc_qty)
                        if not ok and reason not in errors:
                            errors.append(reason)
                    max_qty = _live_acc_max.get(acc_label)
                    if max_qty is not None and acc_qty > max_qty:
                        msg = f"Maximum {max_qty} unit(s) of '{acc_label}' allowed per withdrawal."
                        if msg not in errors:
                            errors.append(msg)

        if transaction_type == 'Return':
            if pistol:
                fresh_pistol = Pistol.objects.get(pk=pistol.pk)
                ok, reason = fresh_pistol.can_be_returned(personnel.Personnel_ID if personnel else None)
                if not ok and reason not in errors:
                    errors.append(reason)
                if personnel:
                    ok2, reason2 = personnel.can_return_pistol(fresh_pistol.item_id)
                    if not ok2 and reason2 not in errors:
                        errors.append(reason2)
            if rifle:
                fresh_rifle = Rifle.objects.get(pk=rifle.pk)
                ok, reason = fresh_rifle.can_be_returned(personnel.Personnel_ID if personnel else None)
                if not ok and reason not in errors:
                    errors.append(reason)
                if personnel:
                    ok2, reason2 = personnel.can_return_rifle(fresh_rifle.item_id)
                    if not ok2 and reason2 not in errors:
                        errors.append(reason2)

            # BINDING RULE (form-level): When returning a pistol, ALL unreturned consumables
            # that were issued together on the same TransactionLog must be included in this
            # return. Operator cannot return the weapon alone and leave ammo/accessories open.
            from .models import TransactionLogs as _TL
            if pistol and personnel:
                _pistol_open_log = _TL.objects.filter(
                    personnel_id=personnel,
                    withdraw_pistol=pistol,
                    return_pistol__isnull=True,
                    log_status__in=['Open', 'Partially Returned'],
                ).order_by('-withdraw_pistol_timestamp').first()
                if _pistol_open_log:
                    _missing = []
                    if _pistol_open_log.withdraw_pistol_magazine_id and not _pistol_open_log.return_pistol_magazine_id:
                        if not pistol_magazine:
                            _missing.append(
                                f"Pistol Magazine ×{_pistol_open_log.withdraw_pistol_magazine_quantity}"
                            )
                    if _pistol_open_log.withdraw_pistol_ammunition_id and not _pistol_open_log.return_pistol_ammunition_id:
                        if not pistol_ammunition:
                            _missing.append(
                                f"Pistol Ammunition ×{_pistol_open_log.withdraw_pistol_ammunition_quantity} rounds"
                            )
                    if _pistol_open_log.withdraw_pistol_holster_quantity and not _pistol_open_log.return_pistol_holster_quantity:
                        if not pistol_holster_quantity:
                            _missing.append(
                                f"Pistol Holster ×{_pistol_open_log.withdraw_pistol_holster_quantity}"
                            )
                    if _pistol_open_log.withdraw_magazine_pouch_quantity and not _pistol_open_log.return_magazine_pouch_quantity:
                        if not magazine_pouch_quantity:
                            _missing.append(
                                f"Magazine Pouch ×{_pistol_open_log.withdraw_magazine_pouch_quantity}"
                            )
                    if _missing:
                        errors.append(
                            "Cannot return the pistol without also returning all items issued with it. "
                            "The following must be included in this return: " + "; ".join(_missing) + "."
                        )

            # BINDING RULE (form-level): When returning a rifle, ALL unreturned consumables
            # that were issued together on the same TransactionLog must be included in this return.
            if rifle and personnel:
                _rifle_open_log = _TL.objects.filter(
                    personnel_id=personnel,
                    withdraw_rifle=rifle,
                    return_rifle__isnull=True,
                    log_status__in=['Open', 'Partially Returned'],
                ).order_by('-withdraw_rifle_timestamp').first()
                if _rifle_open_log:
                    _missing = []
                    if _rifle_open_log.withdraw_rifle_magazine_id and not _rifle_open_log.return_rifle_magazine_id:
                        _required_qty = _rifle_open_log.withdraw_rifle_magazine_quantity or 0
                        _returned_qty = rifle_magazine_quantity or 0
                        if not rifle_magazine or _returned_qty < _required_qty:
                            _missing.append(
                                f"Rifle Magazine ×{_required_qty} (returned: {_returned_qty})"
                            )
                    if _rifle_open_log.withdraw_rifle_ammunition_id and not _rifle_open_log.return_rifle_ammunition_id:
                        _required_qty = _rifle_open_log.withdraw_rifle_ammunition_quantity or 0
                        _returned_qty = rifle_ammunition_quantity or 0
                        if not rifle_ammunition or _returned_qty < _required_qty:
                            _missing.append(
                                f"Rifle Ammunition ×{_required_qty} rounds (returned: {_returned_qty})"
                            )
                    if _rifle_open_log.withdraw_rifle_sling_quantity and not _rifle_open_log.return_rifle_sling_quantity:
                        _required_qty = _rifle_open_log.withdraw_rifle_sling_quantity or 0
                        _returned_qty = rifle_sling_quantity or 0
                        if _returned_qty < _required_qty:
                            _missing.append(
                                f"Rifle Sling ×{_required_qty} (returned: {_returned_qty})"
                            )
                    if _rifle_open_log.withdraw_bandoleer_quantity and not _rifle_open_log.return_bandoleer_quantity:
                        _required_qty = _rifle_open_log.withdraw_bandoleer_quantity or 0
                        _returned_qty = bandoleer_quantity or 0
                        if _returned_qty < _required_qty:
                            _missing.append(
                                f"Bandoleer ×{_required_qty} (returned: {_returned_qty})"
                            )
                    if _missing:
                        errors.append(
                            "Cannot return the rifle without also returning all items issued with it. "
                            "The following must be included in this return: " + "; ".join(_missing) + "."
                        )

            # FIX ISSUE 14: Validate magazine/ammo/accessory returns have a matching open log.
            # This mirrors the model-level validation in Transaction.clean() but runs at
            # form level so errors are shown cleanly in the admin UI before any DB write.
            # NOTE: uses _TL alias (imported at the top of this block) — do NOT re-import
            # TransactionLogs as a bare name here; that creates an UnboundLocalError on the
            # module-level usage at line ~99 because Python treats bare-name imports as local
            # for the entire function scope, even when the import is inside an if-branch.
            if pistol_magazine and personnel:
                open_log = _TL.objects.filter(
                    personnel_id=personnel,
                    withdraw_pistol_magazine=pistol_magazine,
                    return_pistol_magazine__isnull=True,
                ).order_by('-withdraw_pistol_magazine_timestamp').first()
                if not open_log:
                    errors.append(
                        f"No open withdrawal record found for pistol magazine '{pistol_magazine}' for "
                        f"personnel {personnel.Personnel_ID}."
                    )
                elif (pistol_magazine_quantity or 0) <= 0:
                    errors.append(
                        f"Return quantity must be greater than 0 for pistol magazine '{pistol_magazine}'."
                    )
                elif (pistol_magazine_quantity or 0) > (open_log.withdraw_pistol_magazine_quantity or 0):
                    errors.append(
                        f"Return quantity ({pistol_magazine_quantity}) exceeds the originally withdrawn "
                        f"quantity ({open_log.withdraw_pistol_magazine_quantity}) for pistol magazine "
                        f"'{pistol_magazine}'. You cannot return more than was issued."
                    )
            if rifle_magazine and personnel:
                open_log = _TL.objects.filter(
                    personnel_id=personnel,
                    withdraw_rifle_magazine=rifle_magazine,
                    return_rifle_magazine__isnull=True,
                ).order_by('-withdraw_rifle_magazine_timestamp').first()
                if not open_log:
                    errors.append(
                        f"No open withdrawal record found for rifle magazine '{rifle_magazine}' for "
                        f"personnel {personnel.Personnel_ID}."
                    )
                elif (rifle_magazine_quantity or 0) <= 0:
                    errors.append(
                        f"Return quantity must be greater than 0 for rifle magazine '{rifle_magazine}'."
                    )
                elif (rifle_magazine_quantity or 0) > (open_log.withdraw_rifle_magazine_quantity or 0):
                    errors.append(
                        f"Return quantity ({rifle_magazine_quantity}) exceeds the originally withdrawn "
                        f"quantity ({open_log.withdraw_rifle_magazine_quantity}) for rifle magazine "
                        f"'{rifle_magazine}'. You cannot return more than was issued."
                    )
            if pistol_ammunition and personnel:
                open_log = _TL.objects.filter(
                    personnel_id=personnel,
                    withdraw_pistol_ammunition=pistol_ammunition,
                    return_pistol_ammunition__isnull=True,
                ).order_by('-withdraw_pistol_ammunition_timestamp').first()
                if not open_log:
                    errors.append(
                        f"No open withdrawal record found for pistol ammunition '{pistol_ammunition}' for "
                        f"personnel {personnel.Personnel_ID}."
                    )
                elif (pistol_ammunition_quantity or 0) <= 0:
                    errors.append(
                        f"Return quantity must be greater than 0 for pistol ammunition '{pistol_ammunition}'."
                    )
                elif (pistol_ammunition_quantity or 0) > (open_log.withdraw_pistol_ammunition_quantity or 0):
                    errors.append(
                        f"Return quantity ({pistol_ammunition_quantity}) exceeds the originally withdrawn "
                        f"quantity ({open_log.withdraw_pistol_ammunition_quantity}) for pistol ammunition "
                        f"'{pistol_ammunition}'. You cannot return more rounds than were issued."
                    )
            if rifle_ammunition and personnel:
                open_log = _TL.objects.filter(
                    personnel_id=personnel,
                    withdraw_rifle_ammunition=rifle_ammunition,
                    return_rifle_ammunition__isnull=True,
                ).order_by('-withdraw_rifle_ammunition_timestamp').first()
                if not open_log:
                    errors.append(
                        f"No open withdrawal record found for rifle ammunition '{rifle_ammunition}' for "
                        f"personnel {personnel.Personnel_ID}."
                    )
                elif (rifle_ammunition_quantity or 0) <= 0:
                    errors.append(
                        f"Return quantity must be greater than 0 for rifle ammunition '{rifle_ammunition}'."
                    )
                elif (rifle_ammunition_quantity or 0) > (open_log.withdraw_rifle_ammunition_quantity or 0):
                    errors.append(
                        f"Return quantity ({rifle_ammunition_quantity}) exceeds the originally withdrawn "
                        f"quantity ({open_log.withdraw_rifle_ammunition_quantity}) for rifle ammunition "
                        f"'{rifle_ammunition}'. You cannot return more rounds than were issued."
                    )
            # Validate each accessory type return against open TransactionLogs using qty-based lookup
            # MINOR FIX: also compare return qty vs originally withdrawn qty (mirrors model-level check).
            _form_acc_returns = [
                (pistol_holster_quantity,  'withdraw_pistol_holster_quantity', 'return_pistol_holster_quantity', 'withdraw_pistol_holster_timestamp',  'Pistol Holster'),
                (magazine_pouch_quantity,  'withdraw_magazine_pouch_quantity', 'return_magazine_pouch_quantity',  'withdraw_magazine_pouch_timestamp',  'Pistol Magazine Pouch'),
                (rifle_sling_quantity,     'withdraw_rifle_sling_quantity',    'return_rifle_sling_quantity',     'withdraw_rifle_sling_timestamp',     'Rifle Sling'),
                (bandoleer_quantity,       'withdraw_bandoleer_quantity',      'return_bandoleer_quantity',       'withdraw_bandoleer_timestamp',       'Bandoleer'),
            ]
            for acc_qty, w_qty_field, r_qty_field, ts_field, acc_label in _form_acc_returns:
                if acc_qty and personnel:
                    filter_kw = {
                        'personnel_id': personnel,
                        f'{w_qty_field}__isnull': False,
                        f'{r_qty_field}__isnull': True,
                    }
                    open_log = _TL.objects.filter(**filter_kw).order_by(f'-{ts_field}').first()
                    if not open_log:
                        errors.append(
                            f"No open withdrawal record found for '{acc_label}' for "
                            f"personnel {personnel.Personnel_ID}. "
                            "Cannot return an item with no matching withdrawal on record."
                        )
                    else:
                        withdrawn_qty = getattr(open_log, w_qty_field) or 0
                        if acc_qty > withdrawn_qty:
                            errors.append(
                                f"Return quantity ({acc_qty}) exceeds the originally withdrawn quantity "
                                f"({withdrawn_qty}) for '{acc_label}'. "
                                "You cannot return more accessories than were issued."
                            )

        # PAR document required when issuance type is PAR — Withdrawal only.
        # Returns inherit the issuance_type from the originating Withdrawal but do not
        # need to re-upload the PAR document that was already filed at issuance.
        issuance_type_val = cleaned_data.get('issuance_type')
        par_document = cleaned_data.get('par_document')
        if (
            transaction_type == 'Withdrawal'
            and issuance_type_val
            and issuance_type_val.startswith('PAR')
            and not par_document
            and not (self.instance and self.instance.pk and self.instance.par_document)
        ):
            errors.append('A PAR document (PDF) must be uploaded when Issuance Type is PAR.')

        if errors:
            raise forms.ValidationError(errors)
        return cleaned_data

# Add TransactionLogsForm for TransactionLogs
class TransactionLogsForm(forms.ModelForm):
    class Meta:
        model = TransactionLogs
        fields = '__all__'


class WithdrawalReturnTransactionForm(TransactionAdminForm):
    """Frontend-facing transaction form — same validation as admin form."""

    purpose_other = forms.CharField(
        required=False,
        label="Other Purpose",
        max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'Enter purpose'}),
    )

    return_by = forms.DateTimeField(
        required=False,
        label="Return By",
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        input_formats=['%Y-%m-%dT%H:%M'],
        help_text="Deadline for returning the issued firearm(s). Required for TR withdrawals.",
    )

    class Meta(TransactionAdminForm.Meta):
        fields = [
            'transaction_type',
            'issuance_type',
            'purpose',
            'purpose_other',
            'personnel',
            'pistol',
            'rifle',
            'pistol_magazine',
            'pistol_magazine_quantity',
            'rifle_magazine',
            'rifle_magazine_quantity',
            'pistol_ammunition',
            'pistol_ammunition_quantity',
            'rifle_ammunition',
            'rifle_ammunition_quantity',
            'pistol_holster_quantity',
            'magazine_pouch_quantity',
            'rifle_sling_quantity',
            'bandoleer_quantity',
            'include_pistol_holster',
            'include_magazine_pouch',
            'include_rifle_sling',
            'include_bandoleer',
            'return_by',
            'par_document',
            'notes',
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def _post_clean(self):
        """Override to convert any unexpected model-level exception into a form error.

        After successful validation, marks the instance with _validated_from_form=True
        so Transaction.save() can skip its redundant self.clean() call and avoid
        running the same DB validation queries three times per form submission.
        """
        try:
            super()._post_clean()
            # Signal save() that model.clean() was already run by the form layer.
            self.instance._validated_from_form = True
        except Exception as _exc:
            import logging as _log_mod
            _log_mod.getLogger(__name__).exception(
                '_post_clean: unexpected exception during model validation: %s', _exc
            )
            self.add_error(None, 'Form submission failed unexpectedly. Please try again.')

    def clean(self):
        cleaned_data = super().clean()
        purpose = cleaned_data.get('purpose')
        purpose_other = cleaned_data.get('purpose_other')
        if purpose == 'Others':
            if not purpose_other:
                self.add_error('purpose_other', 'Please specify the purpose.')
            else:
                cleaned_data['purpose'] = purpose_other
        # Require return_by for TR withdrawals
        txn_type = cleaned_data.get('transaction_type')
        issuance = cleaned_data.get('issuance_type', '')
        return_by = cleaned_data.get('return_by')
        if txn_type == 'Withdrawal' and 'TR' in (issuance or '') and not return_by:
            self.add_error('return_by', 'Return deadline is required for TR withdrawals.')
        # Require PAR document for PAR issuances if setting is enabled
        if txn_type == 'Withdrawal' and 'PAR' in (issuance or ''):
            from armguard.apps.users.models import SystemSettings as _SS2
            if _SS2.get().require_par_document and not cleaned_data.get('par_document'):
                self.add_error('par_document', 'A signed PAR document (PDF) is required for PAR issuances.')
        return cleaned_data
