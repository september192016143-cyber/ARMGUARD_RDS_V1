import logging
import os
import re
import unicodedata

from django.db import models
from django.db import transaction as db_transaction
from django.core.exceptions import ValidationError
from django.apps import apps
from django.utils import timezone
# Import item and personnel models for transaction logic
from armguard.apps.inventory.models import Pistol, Rifle, Magazine, Ammunition, Accessory
from armguard.apps.personnel.models import Personnel

logger = logging.getLogger('armguard.transactions')

# Issuance type Dropdown
ISSUANCE_TYPE_CHOICES = [
    ('PAR (Property Acknowledgement Receipt)', 'PAR (Property Acknowledgement Receipt)'),
    ('TR (Temporary Receipt)', 'TR (Temporary Receipt)'),
]
# Transaction type options
TRANSACTION_TYPE_CHOICES = [
    ('Withdrawal', 'Withdrawal'),
    ('Return', 'Return'),
]

# Log status options for TransactionLogs
LOG_STATUS_CHOICES = [
    ('Open', 'Open'),
    ('Partially Returned', 'Partially Returned'),
    ('Closed', 'Closed'),
]

 # Purpose options (can be expanded as needed)
PURPOSE_CHOICES = [
    ('Duty Sentinel', 'Duty Sentinel'),
    ('Duty Vigil',    'Duty Vigil'),
    ('Duty Security', 'Duty Security'),
    ('Honor Guard',   'Honor Guard'),
    ('Others',        'Others'),
    ('OREX',          'OREX'),
]

def _sanitize_par_upload(instance, filename):
    """
    C5B FIX: Sanitize the uploaded PAR-document filename before Django writes it
    to disk.  Prevents Unicode homoglyph tricks and path-separator injection in
    the *initial* storage name (before the admin renames it to a canonical form).
    """
    basename = os.path.basename(filename)
    # Strip to ASCII and replace anything that isn't [A-Za-z0-9._-] with '_'
    normalized = unicodedata.normalize('NFKD', basename).encode('ascii', 'ignore').decode('ascii')
    safe = re.sub(r'[^\w\-.]', '_', normalized) or 'upload.pdf'
    return f'PAR_PDF/{safe}'


def _validate_pdf_extension(value):
    """Reject uploads that are not PDF files.

    C5 FIX: Validates both file extension AND PDF magic bytes (%PDF header).
    Extension-only checks can be bypassed by renaming a malicious file to .pdf.
    """
    if not value.name.lower().endswith('.pdf'):
        raise ValidationError('Only PDF files are accepted. Please upload a .pdf file.')
    # Check PDF magic bytes — the first 4 bytes of every valid PDF are b'%PDF'
    header = value.read(4)
    value.seek(0)  # Reset file pointer so subsequent reads/saves work correctly
    if header != b'%PDF':
        raise ValidationError('Uploaded file does not appear to be a valid PDF.')


class Transaction(models.Model):
    """
    Represents a single transaction event for issuing or returning items to/from armguard.apps.personnel.
    Handles business rules for issuing/returning pistols, rifles, magazines, ammunition, and accessories.
    On save, updates related item and personnel records, and creates/updates TransactionLogs.
    """
    transaction_id = models.AutoField(primary_key=True)  # Unique transaction identifier
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)  # Withdrawal or Return
    
    issuance_type = models.CharField(
        max_length=100,
        choices=ISSUANCE_TYPE_CHOICES,
        blank=True,
        null=True,
        help_text="Issuance document type (PAR or TR)."
    )

    # Purpose for this transaction. Choices are enforced at the form/UI level only.
    # Storing choices on the model field prevented saving custom 'Others' text (BUG).
    purpose = models.CharField(
        max_length=100,
        blank=False,
        null=False,
        default='Others',
        help_text="Purpose for this transaction. Custom values are allowed when 'Others' is selected."
    )
    purpose_other = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="If 'Others' is selected, specify the custom purpose."
    )
    
    # Item fields (only one or more may be set per transaction).
    # FIX A: SET_NULL (not CASCADE) so that removing an item from inventory does NOT
    # cascade-delete the transaction records that referenced it. History is permanent.
    pistol = models.ForeignKey(Pistol, on_delete=models.SET_NULL, null=True, blank=True)
    rifle = models.ForeignKey(Rifle, on_delete=models.SET_NULL, null=True, blank=True)
    pistol_magazine = models.ForeignKey(
        Magazine, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pistol_magazine_transactions',
        limit_choices_to={'weapon_type': 'Pistol'},
        help_text="Pistol magazine pool."
    )
    pistol_magazine_quantity = models.PositiveIntegerField(null=True, blank=True)
    rifle_magazine = models.ForeignKey(
        Magazine, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='rifle_magazine_transactions',
        limit_choices_to={'weapon_type': 'Rifle'},
        help_text="Rifle magazine pool."
    )
    rifle_magazine_quantity = models.PositiveIntegerField(null=True, blank=True)
    pistol_ammunition = models.ForeignKey(
        Ammunition, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pistol_ammunition_transactions',
        limit_choices_to={'type__in': ['Cal.45 Ball 433 Ctg', 'M882 9x19mm Ball 435 Ctg']},
        help_text="Pistol ammunition pool."
    )
    pistol_ammunition_quantity = models.PositiveIntegerField(null=True, blank=True)
    rifle_ammunition = models.ForeignKey(
        Ammunition, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='rifle_ammunition_transactions',
        limit_choices_to={'type__in': ['M193 5.56mm Ball 428 Ctg', 'M855 5.56mm Ball 429 Ctg', 'M80 7.62x51mm Ball 431 Ctg']},
        help_text="Rifle ammunition pool."
    )
    rifle_ammunition_quantity = models.PositiveIntegerField(null=True, blank=True)
    # Accessory fields — quantity-only per type; no FK to Accessory pool.
    # The save() method finds the pool by type name and adjusts its quantity.
    pistol_holster_quantity = models.PositiveIntegerField(
        null=True, blank=True, help_text="Number of holsters to issue/return (max 1)."
    )
    magazine_pouch_quantity = models.PositiveIntegerField(
        null=True, blank=True, help_text="Number of magazine pouches to issue/return (max 3)."
    )
    rifle_sling_quantity = models.PositiveIntegerField(
        null=True, blank=True, help_text="Number of rifle slings to issue/return (max 1)."
    )
    bandoleer_quantity = models.PositiveIntegerField(
        null=True, blank=True, help_text="Number of bandoleers to issue/return (max 1)."
    )
    # FIX B: PROTECT prevents deletion of a Personnel record that has transaction history.
    # Personnel with transactions must be deactivated (status='Inactive'), not deleted.
    personnel = models.ForeignKey(Personnel, on_delete=models.PROTECT, null=False, blank=False)  # Personnel involved
    timestamp = models.DateTimeField(auto_now_add=True)  # When transaction was created
    transaction_personnel = models.CharField(max_length=100, null=True, blank=True)  # System user who performed transaction
    notes = models.TextField(
        blank=True, null=True,
        help_text="Optional remarks or notes about this transaction"
    )
    par_document = models.FileField(
        upload_to=_sanitize_par_upload,
        blank=True,
        null=True,
        validators=[_validate_pdf_extension],
        help_text="Required for PAR issuance: upload signed PAR document (PDF). "
                  "File will be renamed to PAR_rank_lastname_transactionID.pdf automatically."
    )
    return_by = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Deadline for returning the issued firearm(s). Applicable to TR (Temporary Receipt) withdrawals."
    )
    # REC-09: Track when the record was last modified (creation is covered by timestamp).
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Auto-set to the current time whenever this transaction record is saved."
    )

    class Meta:
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        # C8: Explicit fine-grained permissions beyond default add/change/delete/view.
        permissions = [
            ("can_process_withdrawal", "Can process item withdrawals"),
            ("can_process_return", "Can process item returns"),
            ("can_view_transaction_logs", "Can view transaction logs"),
        ]
        # REC-10: Composite indexes to accelerate analytics date-range and duty-type queries.
        indexes = [
            models.Index(fields=['transaction_type', 'timestamp'], name='txn_type_ts_idx'),
            models.Index(fields=['transaction_type', 'purpose', 'timestamp'], name='txn_type_purpose_ts_idx'),
            models.Index(fields=['personnel_id', 'transaction_type', 'timestamp'], name='txn_person_type_ts_idx'),
        ]

    def __str__(self):
        """
        String representation showing type and timestamp in local timezone.
        """
        # Convert timestamp to local timezone (Asia/Manila)
        local_timestamp = timezone.localtime(self.timestamp)
        return f"{self.transaction_type} - {local_timestamp}"


    def clean(self):
        """
        Validates all business rules for a Transaction.
        Called by Django admin forms via full_clean(), ensuring errors
        are displayed cleanly to the user before any data is saved.
        Business rules are only enforced on new records (not edits).
        """
        # --- Structural validation (always enforced) ---
        # At least one item must be present (pistol, rifle, magazine, ammunition, or accessory)
        has_any_item = any([
            getattr(self, "pistol", None),
            getattr(self, "rifle", None),
            getattr(self, "pistol_magazine", None),
            getattr(self, "rifle_magazine", None),
            getattr(self, "pistol_ammunition", None),
            getattr(self, "rifle_ammunition", None),
            self.pistol_holster_quantity,
            self.magazine_pouch_quantity,
            self.rifle_sling_quantity,
            self.bandoleer_quantity,
        ])
        if not has_any_item:
            raise ValidationError('At least one item (Pistol, Rifle, Magazine, Ammunition, or Accessory) must be selected for a transaction.')
        if not getattr(self, "personnel", None):
            raise ValidationError('Personnel is required for every transaction.')

        # --- Purpose validation (always enforced) ---
        # purpose must be one of the known choices, OR 'Others' with a non-empty purpose_other.
        _valid_purposes = {p for p, _ in PURPOSE_CHOICES}
        purpose = (self.purpose or '').strip()
        if not purpose:
            raise ValidationError("Purpose is required.")
        if purpose not in _valid_purposes:
            raise ValidationError(
                f"Invalid purpose '{purpose}'. Choose one of: {', '.join(sorted(_valid_purposes))}."
            )
        if purpose == 'Others' and not (self.purpose_other or '').strip():
            raise ValidationError("Please specify the purpose when 'Others' is selected.")

        # --- Business rules (only for new transactions) ---
        # Only enforce business rules for new records (not edits)
        if self.pk:
            return  # Skip re-validation on existing records

        # Withdrawal rules
        if self.transaction_type == 'Withdrawal':
            # Pistol: personnel must not already have one, and item must be available
            if self.pistol:
                # Check if personnel already has a pistol issued
                if self.personnel.has_pistol_issued():
                    raise ValidationError(
                        f"Personnel {self.personnel.Personnel_ID} already has pistol "
                        f"'{self.personnel.pistol_item_issued}' issued. "
                        "Only one pistol can be issued per personnel at a time."
                    )
                # Check if pistol can be withdrawn (status, etc.)
                can_withdraw, reason = self.pistol.can_be_withdrawn()
                if not can_withdraw:
                    raise ValidationError(reason)
            # Rifle: personnel must not already have one, and item must be available
            if self.rifle:
                if self.personnel.has_rifle_issued():
                    raise ValidationError(
                        f"Personnel {self.personnel.Personnel_ID} already has rifle "
                        f"'{self.personnel.rifle_item_issued}' issued. "
                        "Only one rifle can be issued per personnel at a time."
                    )
                can_withdraw, reason = self.rifle.can_be_withdrawn()
                if not can_withdraw:
                    raise ValidationError(reason)
            # Pistol magazine: must have sufficient quantity
            if self.pistol_magazine:
                qty = self.pistol_magazine_quantity or 0
                if qty <= 0:
                    raise ValidationError('Pistol magazine quantity must be greater than 0 for withdrawal.')
                ok, reason = self.pistol_magazine.can_be_withdrawn(qty)
                if not ok:
                    raise ValidationError(reason)
            # Rifle magazine: must have sufficient quantity
            if self.rifle_magazine:
                qty = self.rifle_magazine_quantity or 0
                if qty <= 0:
                    raise ValidationError('Rifle magazine quantity must be greater than 0 for withdrawal.')
                ok, reason = self.rifle_magazine.can_be_withdrawn(qty)
                if not ok:
                    raise ValidationError(reason)
            # Pistol ammunition: must have sufficient quantity
            if self.pistol_ammunition:
                qty = self.pistol_ammunition_quantity or 0
                if qty <= 0:
                    raise ValidationError('Pistol ammunition quantity must be greater than 0 for withdrawal.')
                ok, reason = self.pistol_ammunition.can_be_withdrawn(qty)
                if not ok:
                    raise ValidationError(reason)
            # Rifle ammunition: must have sufficient quantity
            if self.rifle_ammunition:
                qty = self.rifle_ammunition_quantity or 0
                if qty <= 0:
                    raise ValidationError('Rifle ammunition quantity must be greater than 0 for withdrawal.')
                ok, reason = self.rifle_ammunition.can_be_withdrawn(qty)
                if not ok:
                    raise ValidationError(reason)
            # Accessories: each type validated independently by type-name pool lookup
            from armguard.apps.inventory.models import _get_accessory_max_qty, Accessory
            _live_acc_max = _get_accessory_max_qty()
            _acc_type_qty = [
                ('Pistol Holster',        self.pistol_holster_quantity),
                ('Pistol Magazine Pouch', self.magazine_pouch_quantity),
                ('Rifle Sling',           self.rifle_sling_quantity),
                ('Bandoleer',             self.bandoleer_quantity),
            ]
            for acc_type, acc_qty in _acc_type_qty:
                if acc_qty:
                    acc_pool = Accessory.objects.filter(type=acc_type).first()
                    if acc_pool:
                        ok, reason = acc_pool.can_be_withdrawn(acc_qty)
                        if not ok:
                            raise ValidationError(reason)
                    max_qty = _live_acc_max.get(acc_type)
                    if max_qty is not None and acc_qty > max_qty:
                        raise ValidationError(
                            f"Maximum {max_qty} unit(s) of '{acc_type}' may be issued "
                            f"per withdrawal (spec limit). Requested: {acc_qty}."
                        )

            # ── Ammo-weapon caliber compatibility ─────────────────────────────
            from armguard.apps.inventory.models import AMMO_WEAPON_COMPATIBILITY
            if self.pistol_ammunition and self.pistol:
                ammo_type = self.pistol_ammunition.type
                allowed_weapons = AMMO_WEAPON_COMPATIBILITY.get(ammo_type, [])
                if allowed_weapons and self.pistol.model not in allowed_weapons:
                    raise ValidationError(
                        f"Ammunition '{ammo_type}' is not compatible with "
                        f"'{self.pistol.model}'. Allowed weapons: {', '.join(allowed_weapons)}."
                    )
            if self.rifle_ammunition and self.rifle:
                ammo_type = self.rifle_ammunition.type
                allowed_weapons = AMMO_WEAPON_COMPATIBILITY.get(ammo_type, [])
                if allowed_weapons and self.rifle.model not in allowed_weapons:
                    raise ValidationError(
                        f"Ammunition '{ammo_type}' is not compatible with "
                        f"'{self.rifle.model}'. Allowed weapons: {', '.join(allowed_weapons)}."
                    )

            # ── Magazine quantity caps ─────────────────────────────────────────
            # L4 FIX: Use _get_magazine_max_qty() so Django-settings overrides
            # are respected at call time rather than at module import time.
            from armguard.apps.inventory.models import _get_magazine_max_qty
            _mag_caps = _get_magazine_max_qty()
            if self.pistol_magazine and self.pistol_magazine_quantity:
                max_mag = _mag_caps.get('Pistol')
                if max_mag and self.pistol_magazine_quantity > max_mag:
                    raise ValidationError(
                        f"Maximum {max_mag} pistol magazine(s) may be issued per withdrawal (spec limit). "
                        f"Requested: {self.pistol_magazine_quantity}."
                    )
            if self.rifle_magazine and self.rifle_magazine_quantity:
                max_mag = _mag_caps.get('Rifle')
                if max_mag and self.rifle_magazine_quantity > max_mag:
                    raise ValidationError(
                        f"Maximum {max_mag} rifle magazine(s) may be issued per withdrawal (spec limit). "
                        f"Requested: {self.rifle_magazine_quantity}."
                    )

        # Return rules
        elif self.transaction_type == 'Return':
            # Pistol: must be issued to this personnel, and only they can return it
            if self.pistol:
                # Check if personnel can return this pistol (ownership)
                can_return, reason = self.personnel.can_return_pistol(self.pistol.item_id)
                if not can_return:
                    raise ValidationError(reason)
                # Check if pistol can be returned (status, etc.)
                can_return_item, reason_item = self.pistol.can_be_returned(self.personnel.Personnel_ID)
                if not can_return_item:
                    raise ValidationError(reason_item)
            # Rifle: must be issued to this personnel, and only they can return it
            if self.rifle:
                can_return, reason = self.personnel.can_return_rifle(self.rifle.item_id)
                if not can_return:
                    raise ValidationError(reason)
                can_return_item, reason_item = self.rifle.can_be_returned(self.personnel.Personnel_ID)
                if not can_return_item:
                    raise ValidationError(reason_item)

            # FIX ISSUE 14: Validate that magazine/ammo/accessory returns have a matching open log.
            # This blocks returning items that were never recorded as withdrawn for this personnel.
            # HIGH IMPROVEMENT: Also validates that return qty never exceeds the original withdrawn qty.
            TransactionLogs = apps.get_model('transactions', 'TransactionLogs')

            # BINDING RULE: When returning a pistol, ALL unreturned consumables that were
            # withdrawn together (same TransactionLog record) must be included in this return.
            if self.pistol:
                _pistol_open_log = TransactionLogs.objects.filter(
                    personnel_id=self.personnel,
                    withdraw_pistol=self.pistol,
                    return_pistol__isnull=True,
                    log_status__in=['Open', 'Partially Returned'],
                ).order_by('-withdraw_pistol_timestamp').first()
                if _pistol_open_log:
                    _missing = []
                    # Check magazine
                    if _pistol_open_log.withdraw_pistol_magazine_id and not _pistol_open_log.return_pistol_magazine_id:
                        required_qty = _pistol_open_log.withdraw_pistol_magazine_quantity or 0
                        returned_qty = self.pistol_magazine_quantity or 0
                        if not self.pistol_magazine or returned_qty < required_qty:
                            _missing.append(
                                f"Pistol Magazine '{_pistol_open_log.withdraw_pistol_magazine}' ×{required_qty} (returned: {returned_qty})"
                            )
                    # Check ammunition
                    if _pistol_open_log.withdraw_pistol_ammunition_id and not _pistol_open_log.return_pistol_ammunition_id:
                        required_qty = _pistol_open_log.withdraw_pistol_ammunition_quantity or 0
                        returned_qty = self.pistol_ammunition_quantity or 0
                        if not self.pistol_ammunition or returned_qty < required_qty:
                            _missing.append(
                                f"Pistol Ammunition '{_pistol_open_log.withdraw_pistol_ammunition}' ×{required_qty} rounds (returned: {returned_qty})"
                            )
                    # Check holster
                    if _pistol_open_log.withdraw_pistol_holster_quantity and not _pistol_open_log.return_pistol_holster_quantity:
                        required_qty = _pistol_open_log.withdraw_pistol_holster_quantity or 0
                        returned_qty = self.pistol_holster_quantity or 0
                        if returned_qty < required_qty:
                            _missing.append(
                                f"Pistol Holster ×{required_qty} (returned: {returned_qty})"
                            )
                    # Check magazine pouch
                    if _pistol_open_log.withdraw_magazine_pouch_quantity and not _pistol_open_log.return_magazine_pouch_quantity:
                        required_qty = _pistol_open_log.withdraw_magazine_pouch_quantity or 0
                        returned_qty = self.magazine_pouch_quantity or 0
                        if returned_qty < required_qty:
                            _missing.append(
                                f"Magazine Pouch ×{required_qty} (returned: {returned_qty})"
                            )
                    if _missing:
                        raise ValidationError(
                            "Cannot return the pistol without also returning all items issued with it. "
                            "The following must be included in this return: "
                            + "; ".join(_missing) + "."
                        )

            # BINDING RULE: When returning a rifle, ALL unreturned consumables that were
            # withdrawn together (same TransactionLog record) must be included in this return.
            if self.rifle:
                _rifle_open_log = TransactionLogs.objects.filter(
                    personnel_id=self.personnel,
                    withdraw_rifle=self.rifle,
                    return_rifle__isnull=True,
                    log_status__in=['Open', 'Partially Returned'],
                ).order_by('-withdraw_rifle_timestamp').first()
                if _rifle_open_log:
                    _missing = []
                    if _rifle_open_log.withdraw_rifle_magazine_id and not _rifle_open_log.return_rifle_magazine_id:
                        if not self.rifle_magazine:
                            _missing.append(
                                f"Rifle Magazine '{_rifle_open_log.withdraw_rifle_magazine}'"
                                f" ×{_rifle_open_log.withdraw_rifle_magazine_quantity}"
                            )
                    if _rifle_open_log.withdraw_rifle_ammunition_id and not _rifle_open_log.return_rifle_ammunition_id:
                        if not self.rifle_ammunition:
                            _missing.append(
                                f"Rifle Ammunition '{_rifle_open_log.withdraw_rifle_ammunition}'"
                                f" ×{_rifle_open_log.withdraw_rifle_ammunition_quantity} rounds"
                            )
                    if _rifle_open_log.withdraw_rifle_sling_quantity and not _rifle_open_log.return_rifle_sling_quantity:
                        if not self.rifle_sling_quantity:
                            _missing.append(
                                f"Rifle Sling ×{_rifle_open_log.withdraw_rifle_sling_quantity}"
                            )
                    if _rifle_open_log.withdraw_bandoleer_quantity and not _rifle_open_log.return_bandoleer_quantity:
                        if not self.bandoleer_quantity:
                            _missing.append(
                                f"Bandoleer ×{_rifle_open_log.withdraw_bandoleer_quantity}"
                            )
                    if _missing:
                        raise ValidationError(
                            "Cannot return the rifle without also returning all items issued with it. "
                            "The following must be included in this return: "
                            + "; ".join(_missing) + "."
                        )

            if self.pistol_magazine:
                open_log = TransactionLogs.objects.filter(
                    personnel_id=self.personnel,
                    withdraw_pistol_magazine=self.pistol_magazine,
                    return_pistol_magazine__isnull=True,
                ).order_by('-withdraw_pistol_magazine_timestamp').first()
                if not open_log:
                    raise ValidationError(
                        f"No open withdrawal record found for pistol magazine '{self.pistol_magazine}' for "
                        f"personnel {self.personnel.Personnel_ID}. "
                        "Cannot return an item that has no matching withdrawal on record."
                    )
                return_qty = self.pistol_magazine_quantity or 0
                withdrawn_qty = open_log.withdraw_pistol_magazine_quantity or 0
                if return_qty > withdrawn_qty:
                    raise ValidationError(
                        f"Return quantity ({return_qty}) exceeds withdrawn quantity "
                        f"({withdrawn_qty}) for pistol magazine '{self.pistol_magazine}'."
                    )
            if self.rifle_magazine:
                open_log = TransactionLogs.objects.filter(
                    personnel_id=self.personnel,
                    withdraw_rifle_magazine=self.rifle_magazine,
                    return_rifle_magazine__isnull=True,
                ).order_by('-withdraw_rifle_magazine_timestamp').first()
                if not open_log:
                    raise ValidationError(
                        f"No open withdrawal record found for rifle magazine '{self.rifle_magazine}' for "
                        f"personnel {self.personnel.Personnel_ID}. "
                        "Cannot return an item that has no matching withdrawal on record."
                    )
                return_qty = self.rifle_magazine_quantity or 0
                withdrawn_qty = open_log.withdraw_rifle_magazine_quantity or 0
                if return_qty > withdrawn_qty:
                    raise ValidationError(
                        f"Return quantity ({return_qty}) exceeds withdrawn quantity "
                        f"({withdrawn_qty}) for rifle magazine '{self.rifle_magazine}'."
                    )
            if self.pistol_ammunition:
                open_log = TransactionLogs.objects.filter(
                    personnel_id=self.personnel,
                    withdraw_pistol_ammunition=self.pistol_ammunition,
                    return_pistol_ammunition__isnull=True,
                ).order_by('-withdraw_pistol_ammunition_timestamp').first()
                if not open_log:
                    raise ValidationError(
                        f"No open withdrawal record found for pistol ammunition '{self.pistol_ammunition}' for "
                        f"personnel {self.personnel.Personnel_ID}. "
                        "Cannot return an item that has no matching withdrawal on record."
                    )
                return_qty = self.pistol_ammunition_quantity or 0
                withdrawn_qty = open_log.withdraw_pistol_ammunition_quantity or 0
                if return_qty > withdrawn_qty:
                    raise ValidationError(
                        f"Return quantity ({return_qty}) exceeds withdrawn quantity "
                        f"({withdrawn_qty}) for pistol ammunition '{self.pistol_ammunition}'."
                    )
            if self.rifle_ammunition:
                open_log = TransactionLogs.objects.filter(
                    personnel_id=self.personnel,
                    withdraw_rifle_ammunition=self.rifle_ammunition,
                    return_rifle_ammunition__isnull=True,
                ).order_by('-withdraw_rifle_ammunition_timestamp').first()
                if not open_log:
                    raise ValidationError(
                        f"No open withdrawal record found for rifle ammunition '{self.rifle_ammunition}' for "
                        f"personnel {self.personnel.Personnel_ID}. "
                        "Cannot return an item that has no matching withdrawal on record."
                    )
                return_qty = self.rifle_ammunition_quantity or 0
                withdrawn_qty = open_log.withdraw_rifle_ammunition_quantity or 0
                if return_qty > withdrawn_qty:
                    raise ValidationError(
                        f"Return quantity ({return_qty}) exceeds withdrawn quantity "
                        f"({withdrawn_qty}) for rifle ammunition '{self.rifle_ammunition}'."
                    )
            # Validate each accessory type return using quantity-based log lookup
            _acc_return_checks = [
                (self.pistol_holster_quantity, 'withdraw_pistol_holster_quantity', 'return_pistol_holster_quantity',  'withdraw_pistol_holster_timestamp',  'Pistol Holster'),
                (self.magazine_pouch_quantity,  'withdraw_magazine_pouch_quantity', 'return_magazine_pouch_quantity',  'withdraw_magazine_pouch_timestamp',  'Pistol Magazine Pouch'),
                (self.rifle_sling_quantity,     'withdraw_rifle_sling_quantity',    'return_rifle_sling_quantity',     'withdraw_rifle_sling_timestamp',     'Rifle Sling'),
                (self.bandoleer_quantity,       'withdraw_bandoleer_quantity',      'return_bandoleer_quantity',       'withdraw_bandoleer_timestamp',       'Bandoleer'),
            ]
            for acc_qty, w_qty_field, r_qty_field, ts_field, acc_label in _acc_return_checks:
                if acc_qty:
                    filter_kw = {
                        'personnel_id': self.personnel,
                        f'{w_qty_field}__isnull': False,
                        f'{r_qty_field}__isnull': True,
                    }
                    open_log = TransactionLogs.objects.filter(**filter_kw).order_by(f'-{ts_field}').first()
                    if not open_log:
                        raise ValidationError(
                            f"No open withdrawal record found for '{acc_label}' for "
                            f"personnel {self.personnel.Personnel_ID}. "
                            "Cannot return an item that has no matching withdrawal on record."
                        )
                    withdrawn_qty = getattr(open_log, w_qty_field) or 0
                    if acc_qty > withdrawn_qty:
                        raise ValidationError(
                            f"Return quantity ({acc_qty}) exceeds the originally withdrawn quantity "
                            f"({withdrawn_qty}) for '{acc_label}'. "
                            "You cannot return more accessories than were issued."
                        )


    def save(self, *args, **kwargs):
        """
        C6 FIX: Thin orchestrator — validates, persists, then delegates all
        side effects to the service layer in transactions/services.py.
        Method reduced from 769 lines to ~40 lines; all business logic lives
        in focused, unit-testable service functions.
        """
        from .services import (
            propagate_issuance_type,
            sync_personnel_and_items,
            adjust_consumable_quantities,
            create_withdrawal_log,
            update_return_logs,
            write_audit_entry,
        )
        user = kwargs.pop('user', None)
        username = user.username if user and hasattr(user, 'username') else None

        # Auto-set operator from logged-in user
        if username and not self.transaction_personnel:
            self.transaction_personnel = username

        # Enforce business rules (safety net for direct save() calls not going through
        # a form; form's _post_clean() sets _validated_from_form=True to skip this
        # redundant run and avoid triple execution of the same DB validation queries).
        if not self.pk and not getattr(self, '_validated_from_form', False):
            self.clean()

        # M6: Inherit issuance_type from the matching Withdrawal when not set
        propagate_issuance_type(self)

        # Auto-set return_by for TR withdrawals using the configured default hours
        if (self.transaction_type == 'Withdrawal' and
                self.issuance_type and 'TR' in self.issuance_type and
                not self.return_by):
            from datetime import timedelta
            from django.utils import timezone as _tz
            try:
                from armguard.apps.users.models import SystemSettings as _SS
                _tr_hours = _SS.get().tr_default_return_hours or 24
            except Exception:
                _tr_hours = 24
            self.return_by = (self.timestamp or _tz.now()) + timedelta(hours=_tr_hours)
        elif self.transaction_type == 'Return':
            # Return transactions have no deadline of their own; the deadline
            # lives on the originating Withdrawal.  Clear any accidental value
            # (e.g. a stale form field that was hidden but not cleared).
            self.return_by = None

        TransactionLogs = apps.get_model('transactions', 'TransactionLogs')

        with db_transaction.atomic():
            # L10: Row-level locks prevent double-issuance race under PostgreSQL.
            # SQLite serialises all writers at the file level inside atomic(), so
            # select_for_update() is skipped — it raises NotSupportedError on SQLite.
            from django.db import connection as _conn
            def _lock(qs):
                return qs.select_for_update() if _conn.vendor != 'sqlite' else qs

            if self.personnel_id:
                _lock(Personnel.objects.filter(pk=self.personnel_id)).get()
            if self.pistol_id:
                _lock(Pistol.objects.filter(pk=self.pistol_id)).get()
            if self.rifle_id:
                _lock(Rifle.objects.filter(pk=self.rifle_id)).get()
            # L10-EXT: Lock consumable pool rows to prevent double-adjustment race
            # conditions on Magazine, Ammunition, and Accessory pools.
            if self.pistol_magazine_id:
                _lock(Magazine.objects.filter(pk=self.pistol_magazine_id)).get()
            if self.rifle_magazine_id and self.rifle_magazine_id != self.pistol_magazine_id:
                _lock(Magazine.objects.filter(pk=self.rifle_magazine_id)).get()
            if self.pistol_ammunition_id:
                _lock(Ammunition.objects.filter(pk=self.pistol_ammunition_id)).get()
            if self.rifle_ammunition_id and self.rifle_ammunition_id != self.pistol_ammunition_id:
                _lock(Ammunition.objects.filter(pk=self.rifle_ammunition_id)).get()
            for _acc_type, _acc_qty in [
                ('Pistol Holster',        self.pistol_holster_quantity),
                ('Pistol Magazine Pouch', self.magazine_pouch_quantity),
                ('Rifle Sling',           self.rifle_sling_quantity),
                ('Bandoleer',             self.bandoleer_quantity),
            ]:
                if _acc_qty:
                    _lock(Accessory.objects.filter(type=_acc_type)).first()

            super().save(*args, **kwargs)

            sync_personnel_and_items(self, username)
            adjust_consumable_quantities(self)

            if self.transaction_type == 'Withdrawal':
                create_withdrawal_log(self, username, TransactionLogs)
            elif self.transaction_type == 'Return':
                update_return_logs(self, username, user, TransactionLogs)

            write_audit_entry(self, username)


    def get_item_display(self):
        """
        Returns a string label for the primary item in this transaction.
        Used for display purposes in admin or UI.
        """
        if self.pistol:
            return str(self.pistol)
        if self.rifle:
            return str(self.rifle)
        if self.pistol_magazine:
            return str(self.pistol_magazine)
        if self.rifle_magazine:
            return str(self.rifle_magazine)
        if self.pistol_ammunition:
            return str(self.pistol_ammunition)
        if self.rifle_ammunition:
            return str(self.rifle_ammunition)
        if self.pistol_holster_quantity:
            return f'Pistol Holster ×{self.pistol_holster_quantity}'
        if self.magazine_pouch_quantity:
            return f'Pistol Magazine Pouch ×{self.magazine_pouch_quantity}'
        if self.rifle_sling_quantity:
            return f'Rifle Sling ×{self.rifle_sling_quantity}'
        if self.bandoleer_quantity:
            return f'Bandoleer ×{self.bandoleer_quantity}'
        return None



class TransactionLogs(models.Model):
    """
    Log record pairing withdrawal and return events per item per personnel.
    - Each record tracks both withdrawal and return events for pistol, rifle, magazine, ammunition, and accessory.
    - If both pistol and rifle are withdrawn in the same transaction, a single log covers both.
    - log_status tracks whether items have been returned:
      - Open: no items returned yet
      - Partially Returned: one of two items returned (from a combined p+r withdrawal)
      - Closed: all withdrawn items returned
    """
    record_id = models.AutoField(primary_key=True)  # Unique log record identifier

    class Meta:
        verbose_name = "Transaction Log"
        verbose_name_plural = "Transaction Logs"
        # REC-01: Composite indexes for the most frequent multi-column filter patterns.
        # Each Return transaction runs one of these queries to find the matching open log.
        indexes = [
            models.Index(
                fields=['personnel_id', 'withdraw_pistol', 'return_pistol'],
                name='tlog_pistol_return_idx'
            ),
            models.Index(
                fields=['personnel_id', 'withdraw_rifle', 'return_rifle'],
                name='tlog_rifle_return_idx'
            ),
            models.Index(
                fields=['personnel_id', 'withdraw_pistol_magazine', 'return_pistol_magazine'],
                name='tlog_pmag_return_idx'
            ),
            models.Index(
                fields=['personnel_id', 'withdraw_rifle_magazine', 'return_rifle_magazine'],
                name='tlog_rmag_return_idx'
            ),
            models.Index(
                fields=['personnel_id', 'log_status'],
                name='tlog_person_status_idx'
            ),
            # 5.8 FIX: Indexes for ammunition return lookups (previously missing).
            # Return transactions filter on (personnel_id, withdraw_*_ammunition, return_*__isnull=True).
            models.Index(
                fields=['personnel_id', 'withdraw_pistol_ammunition', 'return_pistol_ammunition'],
                name='tlog_pammo_return_idx'
            ),
            models.Index(
                fields=['personnel_id', 'withdraw_rifle_ammunition', 'return_rifle_ammunition'],
                name='tlog_rammo_return_idx'
            ),
        ]

    # FIX B: PROTECT prevents deletion of Personnel who have log history.
    personnel_id = models.ForeignKey(Personnel, on_delete=models.PROTECT)  # Personnel involved
    # Withdrawal fields for pistol
    withdrawal_pistol_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='withdrawal_pistol_record'
    )
    # FIX A: All item FKs on TransactionLogs use SET_NULL — deleting an inventory item
    # nullifies the FK cell but preserves the log record itself. History is never lost.
    withdraw_pistol = models.ForeignKey(
        Pistol, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='withdraw_pistol_records'
    )
    withdraw_pistol_timestamp = models.DateTimeField(blank=True, null=True)
    withdraw_pistol_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Withdrawal fields for rifle
    withdrawal_rifle_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='withdrawal_rifle_record'
    )
    withdraw_rifle = models.ForeignKey(
        Rifle, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='withdraw_rifle_records'
    )
    withdraw_rifle_timestamp = models.DateTimeField(blank=True, null=True)
    withdraw_rifle_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Withdrawal fields for pistol magazine
    withdrawal_pistol_magazine_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='withdrawal_pistol_magazine_record'
    )
    withdraw_pistol_magazine = models.ForeignKey(
        Magazine, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='withdraw_pistol_magazine_records',
        limit_choices_to={'weapon_type': 'Pistol'}
    )
    withdraw_pistol_magazine_quantity = models.PositiveIntegerField(null=True, blank=True)
    withdraw_pistol_magazine_timestamp = models.DateTimeField(blank=True, null=True)
    withdraw_pistol_magazine_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Withdrawal fields for rifle magazine
    withdrawal_rifle_magazine_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='withdrawal_rifle_magazine_record'
    )
    withdraw_rifle_magazine = models.ForeignKey(
        Magazine, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='withdraw_rifle_magazine_records',
        limit_choices_to={'weapon_type': 'Rifle'}
    )
    withdraw_rifle_magazine_quantity = models.PositiveIntegerField(null=True, blank=True)
    withdraw_rifle_magazine_timestamp = models.DateTimeField(blank=True, null=True)
    withdraw_rifle_magazine_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Withdrawal fields for pistol ammunition
    withdrawal_pistol_ammunition_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='withdrawal_pistol_ammunition_record'
    )
    withdraw_pistol_ammunition = models.ForeignKey(
        Ammunition, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='withdraw_pistol_ammunition_records',
        limit_choices_to={'type__in': ['Cal.45 Ball 433 Ctg', 'M882 9x19mm Ball 435 Ctg']}
    )
    withdraw_pistol_ammunition_quantity = models.PositiveIntegerField(null=True, blank=True)
    withdraw_pistol_ammunition_timestamp = models.DateTimeField(blank=True, null=True)
    withdraw_pistol_ammunition_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Withdrawal fields for rifle ammunition
    withdrawal_rifle_ammunition_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='withdrawal_rifle_ammunition_record'
    )
    withdraw_rifle_ammunition = models.ForeignKey(
        Ammunition, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='withdraw_rifle_ammunition_records',
        limit_choices_to={'type__in': ['M193 5.56mm Ball 428 Ctg', 'M855 5.56mm Ball 429 Ctg', 'M80 7.62x51mm Ball 431 Ctg']}
    )
    withdraw_rifle_ammunition_quantity = models.PositiveIntegerField(null=True, blank=True)
    withdraw_rifle_ammunition_timestamp = models.DateTimeField(blank=True, null=True)
    withdraw_rifle_ammunition_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Withdrawal fields — Pistol Holster
    withdrawal_pistol_holster_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='withdrawal_pistol_holster_record'
    )
    withdraw_pistol_holster_quantity = models.PositiveIntegerField(null=True, blank=True)
    withdraw_pistol_holster_timestamp = models.DateTimeField(blank=True, null=True)
    withdraw_pistol_holster_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Withdrawal fields — Pistol Magazine Pouch
    withdrawal_magazine_pouch_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='withdrawal_magazine_pouch_record'
    )
    withdraw_magazine_pouch_quantity = models.PositiveIntegerField(null=True, blank=True)
    withdraw_magazine_pouch_timestamp = models.DateTimeField(blank=True, null=True)
    withdraw_magazine_pouch_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Withdrawal fields — Rifle Sling
    withdrawal_rifle_sling_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='withdrawal_rifle_sling_record'
    )
    withdraw_rifle_sling_quantity = models.PositiveIntegerField(null=True, blank=True)
    withdraw_rifle_sling_timestamp = models.DateTimeField(blank=True, null=True)
    withdraw_rifle_sling_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Withdrawal fields — Bandoleer
    withdrawal_bandoleer_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='withdrawal_bandoleer_record'
    )
    withdraw_bandoleer_quantity = models.PositiveIntegerField(null=True, blank=True)
    withdraw_bandoleer_timestamp = models.DateTimeField(blank=True, null=True)
    withdraw_bandoleer_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Return fields for pistol
    return_pistol_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='return_pistol_record'
    )
    return_pistol = models.ForeignKey(
        Pistol, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='return_pistol_records'
    )
    return_pistol_timestamp = models.DateTimeField(blank=True, null=True)
    return_pistol_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Return fields for rifle
    return_rifle_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='return_rifle_record'
    )
    return_rifle = models.ForeignKey(
        Rifle, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='return_rifle_records'
    )
    return_rifle_timestamp = models.DateTimeField(blank=True, null=True)
    return_rifle_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Return fields for pistol magazine
    return_pistol_magazine_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='return_pistol_magazine_record'
    )
    return_pistol_magazine = models.ForeignKey(
        Magazine, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='return_pistol_magazine_records',
        limit_choices_to={'weapon_type': 'Pistol'}
    )
    return_pistol_magazine_quantity = models.PositiveIntegerField(null=True, blank=True)
    return_pistol_magazine_timestamp = models.DateTimeField(blank=True, null=True)
    return_pistol_magazine_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Return fields for rifle magazine
    return_rifle_magazine_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='return_rifle_magazine_record'
    )
    return_rifle_magazine = models.ForeignKey(
        Magazine, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='return_rifle_magazine_records',
        limit_choices_to={'weapon_type': 'Rifle'}
    )
    return_rifle_magazine_quantity = models.PositiveIntegerField(null=True, blank=True)
    return_rifle_magazine_timestamp = models.DateTimeField(blank=True, null=True)
    return_rifle_magazine_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Return fields for pistol ammunition
    return_pistol_ammunition_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='return_pistol_ammunition_record'
    )
    return_pistol_ammunition = models.ForeignKey(
        Ammunition, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='return_pistol_ammunition_records',
        limit_choices_to={'type__in': ['Cal.45 Ball 433 Ctg', 'M882 9x19mm Ball 435 Ctg']}
    )
    return_pistol_ammunition_quantity = models.PositiveIntegerField(null=True, blank=True)
    return_pistol_ammunition_timestamp = models.DateTimeField(blank=True, null=True)
    return_pistol_ammunition_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Return fields for rifle ammunition
    return_rifle_ammunition_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='return_rifle_ammunition_record'
    )
    return_rifle_ammunition = models.ForeignKey(
        Ammunition, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='return_rifle_ammunition_records',
        limit_choices_to={'type__in': ['M193 5.56mm Ball 428 Ctg', 'M855 5.56mm Ball 429 Ctg', 'M80 7.62x51mm Ball 431 Ctg']}
    )
    return_rifle_ammunition_quantity = models.PositiveIntegerField(null=True, blank=True)
    return_rifle_ammunition_timestamp = models.DateTimeField(blank=True, null=True)
    return_rifle_ammunition_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Return fields — Pistol Holster
    return_pistol_holster_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='return_pistol_holster_record'
    )
    return_pistol_holster_quantity = models.PositiveIntegerField(null=True, blank=True)
    return_pistol_holster_timestamp = models.DateTimeField(blank=True, null=True)
    return_pistol_holster_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Return fields — Pistol Magazine Pouch
    return_magazine_pouch_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='return_magazine_pouch_record'
    )
    return_magazine_pouch_quantity = models.PositiveIntegerField(null=True, blank=True)
    return_magazine_pouch_timestamp = models.DateTimeField(blank=True, null=True)
    return_magazine_pouch_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Return fields — Rifle Sling
    return_rifle_sling_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='return_rifle_sling_record'
    )
    return_rifle_sling_quantity = models.PositiveIntegerField(null=True, blank=True)
    return_rifle_sling_timestamp = models.DateTimeField(blank=True, null=True)
    return_rifle_sling_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Return fields — Bandoleer
    return_bandoleer_transaction_id = models.ForeignKey(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='return_bandoleer_record'
    )
    return_bandoleer_quantity = models.PositiveIntegerField(null=True, blank=True)
    return_bandoleer_timestamp = models.DateTimeField(blank=True, null=True)
    return_bandoleer_transaction_personnel = models.CharField(max_length=100, null=True, blank=True)
    # Status of the log (Open, Partially Returned, Closed)
    log_status = models.CharField(
        max_length=20, choices=LOG_STATUS_CHOICES, default='Open',
        help_text="Open: not yet returned. Partially Returned: one of two items returned. Closed: all items returned."
    )
    # Issuance type — copied from the originating withdrawal Transaction on first save.
    # Stored here for direct querying without joining back to Transaction.
    issuance_type = models.CharField(
        max_length=100,
        choices=ISSUANCE_TYPE_CHOICES,
        blank=True,
        null=True,
        help_text="Issuance document type (PAR or TR), copied from the withdrawal transaction."
    )
    notes = models.TextField(
        blank=True, null=True,
        help_text="Optional remarks about this log record"
    )


    def update_log_status(self):
        """
        Computes and sets log_status based on which item types were withdrawn vs returned.

        FIX BUG 4: Previously only checked pistol and rifle, causing magazine/ammo/accessory-
        only log records to remain permanently 'Open' even after all items were returned.
        Now evaluates all five item types (pistol, rifle, magazine, ammunition, accessory).

        Status rules:
          - 'Open'             : no items have been returned yet
          - 'Partially Returned': at least one item returned but not all withdrawn items returned
          - 'Closed'           : every withdrawn item type has a matching return

        Call this method before save() whenever any return field is updated on this record.
        """
        # Map each item type to whether it was withdrawn and whether it was returned
        withdrawn = {
            'pistol':             bool(self.withdraw_pistol_id),
            'rifle':              bool(self.withdraw_rifle_id),
            'pistol_magazine':    bool(self.withdraw_pistol_magazine_id),
            'rifle_magazine':     bool(self.withdraw_rifle_magazine_id),
            'pistol_ammunition':  bool(self.withdraw_pistol_ammunition_id),
            'rifle_ammunition':   bool(self.withdraw_rifle_ammunition_id),
            'pistol_holster':     bool(self.withdraw_pistol_holster_quantity),
            'magazine_pouch':     bool(self.withdraw_magazine_pouch_quantity),
            'rifle_sling':        bool(self.withdraw_rifle_sling_quantity),
            'bandoleer':          bool(self.withdraw_bandoleer_quantity),
        }
        returned = {
            'pistol':             bool(self.return_pistol_id),
            'rifle':              bool(self.return_rifle_id),
            'pistol_magazine':    bool(self.return_pistol_magazine_id),
            'rifle_magazine':     bool(self.return_rifle_magazine_id),
            'pistol_ammunition':  bool(self.return_pistol_ammunition_id),
            'rifle_ammunition':   bool(self.return_rifle_ammunition_id),
            'pistol_holster':     bool(self.return_pistol_holster_quantity),
            'magazine_pouch':     bool(self.return_magazine_pouch_quantity),
            'rifle_sling':        bool(self.return_rifle_sling_quantity),
            'bandoleer':          bool(self.return_bandoleer_quantity),
        }

        total_withdrawn = sum(withdrawn.values())
        # Only count a return as valid if the corresponding item was actually withdrawn
        total_returned = sum(returned[k] for k in withdrawn if withdrawn[k])

        if total_withdrawn == 0:
            # Defensive fallback — no items means nothing to track
            self.log_status = 'Open'
        elif total_returned >= total_withdrawn:
            self.log_status = 'Closed'
        elif total_returned == 0:
            self.log_status = 'Open'
        else:
            self.log_status = 'Partially Returned'


    def save(self, *args, **kwargs):
        """
        Saves the log record, optionally setting transaction personnel fields from the user.
        FIX DIS. 3: Always recomputes log_status before saving to prevent stale status values.
        update_log_status() was previously only called by Transaction.save() on Returns, meaning
        direct admin edits or any other save() call would leave log_status unchanged.
        """
        user = kwargs.pop('user', None)
        # BUG 1 FIX: Only stamp *withdrawal* operator fields on NEW log rows.
        # When update_return_logs() calls lobj.save(user=return_operator), the
        # passed user is the return operator — overwriting withdraw_*_transaction_personnel
        # with that username corrupts the original withdrawal audit trail.
        if user and hasattr(user, 'username'):
            uname = user.username
            if not self.pk:
                # New log row: record the withdrawal operator for all withdrawal fields.
                if self.withdraw_pistol is not None:
                    self.withdraw_pistol_transaction_personnel = uname
                if self.withdraw_rifle is not None:
                    self.withdraw_rifle_transaction_personnel = uname
                if self.withdraw_pistol_magazine is not None:
                    self.withdraw_pistol_magazine_transaction_personnel = uname
                if self.withdraw_rifle_magazine is not None:
                    self.withdraw_rifle_magazine_transaction_personnel = uname
                if self.withdraw_pistol_ammunition is not None:
                    self.withdraw_pistol_ammunition_transaction_personnel = uname
                if self.withdraw_rifle_ammunition is not None:
                    self.withdraw_rifle_ammunition_transaction_personnel = uname
                if self.withdraw_pistol_holster_quantity is not None:
                    self.withdraw_pistol_holster_transaction_personnel = uname
                if self.withdraw_magazine_pouch_quantity is not None:
                    self.withdraw_magazine_pouch_transaction_personnel = uname
                if self.withdraw_rifle_sling_quantity is not None:
                    self.withdraw_rifle_sling_transaction_personnel = uname
                if self.withdraw_bandoleer_quantity is not None:
                    self.withdraw_bandoleer_transaction_personnel = uname
            # Return operator fields are always stamped when return data is present.
            if self.return_pistol is not None:
                self.return_pistol_transaction_personnel = uname
            if self.return_rifle is not None:
                self.return_rifle_transaction_personnel = uname
            if self.return_pistol_magazine is not None:
                self.return_pistol_magazine_transaction_personnel = uname
            if self.return_rifle_magazine is not None:
                self.return_rifle_magazine_transaction_personnel = uname
            if self.return_pistol_ammunition is not None:
                self.return_pistol_ammunition_transaction_personnel = uname
            if self.return_rifle_ammunition is not None:
                self.return_rifle_ammunition_transaction_personnel = uname
            if self.return_pistol_holster_quantity is not None:
                self.return_pistol_holster_transaction_personnel = uname
            if self.return_magazine_pouch_quantity is not None:
                self.return_magazine_pouch_transaction_personnel = uname
            if self.return_rifle_sling_quantity is not None:
                self.return_rifle_sling_transaction_personnel = uname
            if self.return_bandoleer_quantity is not None:
                self.return_bandoleer_transaction_personnel = uname
        # Auto-copy issuance_type from the first available withdrawal Transaction FK.
        # Only set if not already populated — preserves any manual override.
        if not self.issuance_type:
            for txn_fk in [
                self.withdrawal_pistol_transaction_id,
                self.withdrawal_rifle_transaction_id,
                self.withdrawal_pistol_magazine_transaction_id,
                self.withdrawal_rifle_magazine_transaction_id,
                self.withdrawal_pistol_ammunition_transaction_id,
                self.withdrawal_rifle_ammunition_transaction_id,
                self.withdrawal_pistol_holster_transaction_id,
                self.withdrawal_magazine_pouch_transaction_id,
                self.withdrawal_rifle_sling_transaction_id,
                self.withdrawal_bandoleer_transaction_id,
            ]:
                if txn_fk and getattr(txn_fk, 'issuance_type', None):
                    self.issuance_type = txn_fk.issuance_type
                    break
        # Always recompute log_status from actual FK values before writing to DB.
        self.update_log_status()
        super().save(*args, **kwargs)


    def __str__(self):
        """
        String representation showing log record ID, personnel, and status.
        """
        return f"Log #{self.record_id} — {self.personnel_id} [{self.log_status}]"
