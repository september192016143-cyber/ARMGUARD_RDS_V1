import uuid
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from .base_models import SmallArm
# Item Type choices
ITEMS_CHOICES = [
    ('Small Arms', 'Small Arms'),
    ('Ammunition', 'Ammunition'),
    ('Magazines', 'Magazines'),
    ('Accessories', 'Accessories'),
]
# Small arms categories
SMALL_ARMS_CHOICES = [
    ('Pistol', 'Pistol'),
    ('Rifle', 'Rifle'),
]
# Pistol Models
PISTOL_MODELS = [
    ('Glock 17 9mm', 'Glock 17 9mm'),
    ('M1911 Cal.45', 'M1911 Cal.45'),
    ('Armscor Hi Cap Cal.45', 'Armscor Hi Cap Cal.45'),
    ('RIA Hi Cap Cal.45', 'RIA Hi Cap Cal.45'),
    ('M1911 Customized Cal.45', 'M1911 Customized Cal.45'),
]
# Rifle Models
RIFLE_MODELS = [
    ('M4 Carbine DSAR-15 5.56mm', 'M4 Carbine DSAR-15 5.56mm'),
    ('M4 14.5" DGIS EMTAN 5.56mm', 'M4 14.5" DGIS EMTAN 5.56mm'),
    ('M16A1 Rifle 5.56mm', 'M16 Rifle 5.56mm'),
    ('M14 Rifle 7.62mm', 'M14 Rifle 7.62mm'),
    ('M653 Carbine 5.56mm', 'M653 Carbine 5.56mm'),
]
# Accessories
ACCESSORY_TYPES = [
    ('Pistol Magazine Pouch', 'Pistol Magazine Pouch'),
    ('Pistol Holster', 'Pistol Holster'),
    ('Rifle Sling', 'Rifle Sling'),
    ('Bandoleer', 'Bandoleer'),
]
# Ammunition Types
PISTOL_AMMUNITION_TYPES = [
    ('Cal.45 Ball 433 Ctg', 'Cal.45 Ball 433 Ctg'),
    ('M882 9x19mm Ball 435 Ctg', 'M882 9x19mm Ball 435 Ctg'),
]
# Ammunition Types
RIFLE_AMMUNITION_TYPES = [
    ('M193 5.56mm Ball 428 Ctg', 'M193 5.56mm Ball 428 Ctg'),
    ('M855 5.56mm Ball 429 Ctg', 'M855 5.56mm Ball 429 Ctg'),
    ('M80 7.62x51mm Ball 431 Ctg', 'M80 7.62x51mm Ball 431 Ctg'),
]
# Combined ammunition choices (pistol + rifle) — used by Ammunition.type field.
# PISTOL_AMMUNITION_TYPES and RIFLE_AMMUNITION_TYPES are kept separate for JS
# filtering in the admin form (auto-filter ammo dropdown by selected pistol/rifle model).
AMMUNITION_TYPES = PISTOL_AMMUNITION_TYPES + RIFLE_AMMUNITION_TYPES
# Pistol Magazine Types
PISTOL_MAGAZINE_TYPES = [
    ('Pistol Standard', 'Pistol Standard'),
]
# Rifle Magazine Types
RIFLE_MAGAZINE_TYPES = [
    ('Short', 'Short'),
    ('Long', 'Long'),
]
# Combined magazine choices (pistol + rifle) — used by Magazine.type field.
ALL_MAGAZINE_TYPES = PISTOL_MAGAZINE_TYPES + RIFLE_MAGAZINE_TYPES
# Ammo-to-weapon compatibility map.
# Keys are Ammunition.type values; values are lists of allowed pistol/rifle model strings.
# Used by Transaction.clean() to validate that ammo and weapon calibers match.
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
# Standard maximum quantities per accessory type when paired with a weapon.
# Withdrawal validation uses these to cap quantities at the doctrinal limit.
ACCESSORY_MAX_QTY = {
    'Pistol Holster': 1,
    'Pistol Magazine Pouch': 3,
    'Rifle Sling': 1,
    'Bandoleer': 1,
}
# Maximum magazines issuable per weapon type in a single withdrawal.
# L4 FIX: Values are sourced from Django settings so they can be changed
# per deployment without touching model code.


def _get_magazine_max_qty():
    # L4-EXT: Read the live DB value set by the admin via System Settings.
    # Fallback to Django settings constants if DB is unavailable (e.g. during
    # migrations or tests that don't seed SystemSettings).
    try:
        from armguard.apps.users.models import SystemSettings
        s = SystemSettings.get()
        return {
            'Pistol': s.pistol_magazine_max_qty or 4,
            'Rifle':  s.rifle_magazine_max_qty,
        }
    except Exception:
        from django.conf import settings as _s
        return {
            'Pistol': getattr(_s, 'ARMGUARD_PISTOL_MAGAZINE_MAX_QTY', 4),
            'Rifle':  getattr(_s, 'ARMGUARD_RIFLE_MAGAZINE_MAX_QTY', None),
        }
MAGAZINE_MAX_QTY = {
    'Pistol': 4,  # default — overridden at runtime via _get_magazine_max_qty()
    'Rifle': None,
}


def _magazine_max_qty(weapon_type: str):
    """Return the current per-withdrawal magazine cap for *weapon_type*."""
    return _get_magazine_max_qty().get(weapon_type)
#Item status
STATUS_CHOICES = [
    ('Issued', 'Issued'),
    ('Available', 'Available'),
    ('Under Maintenance', 'Under Maintenance'),
    ('For Turn In', 'For Turn In'),
    ('Turned In', 'Turned In'),
    ('Decommissioned', 'Decommissioned'),
]
#Item condition
CONDITION_CHOICES = [
    ('Serviceable', 'Serviceable'),
    ('Unserviceable', 'Unserviceable'),
    ('Lost', 'Lost'),
    ('Tampered', 'Tampered'),
]
# Category model for item classification


class Category(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name
"""# Location model for tracking where items are stored


class Location(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name
"""
# --- Pistol ------------------------------------------------------------------


class Pistol(SmallArm):
    """
    Represents a single pistol unit in the armory inventory.
    Fields are listed first (primary key, attributes, media, audit, status, tracking),
    followed by Meta, then all methods.
    item_id is auto-generated as 'IP-<model_code>-<serial_number>' on first save.
    QR code image is auto-generated from item_id on creation or when item_id changes.
    Issued status is enforced through set_issued() only — never set item_status='Issued'
    directly via admin without going through a Withdrawal Transaction.
    """
    # N7: arm_type used by SmallArm shared methods (clean, can_be_withdrawn, etc.).
    arm_type = 'pistol'
    # -- Primary key and identification ----------------------------------------
    # item_id is set automatically during save(); do not supply manually.
    item_id = models.CharField(max_length=50, primary_key=True, unique=True, blank=False, editable=False)
    item_number = models.CharField(max_length=4, blank=False, help_text="Required. Unique number within the same pistol model (e.g. 0001). Must be entered manually.")
    property_number = models.CharField(max_length=50, blank=True, null=True, unique=True, help_text="Government / property custodian number assigned to this pistol. Leave blank if not yet assigned.")
    # -- Item attributes -------------------------------------------------------
    # C4: FK to Category — enables item classification with referential integrity.
    category = models.ForeignKey(
        'Category',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pistols',
        help_text="Optional category classification for this pistol (e.g., Small Arms)."
    )
    model = models.CharField(max_length=30, choices=PISTOL_MODELS)
    serial_number = models.CharField(max_length=50, unique=True, blank=False)
    # -- Media files -----------------------------------------------------------

    def serial_image_upload_to(instance, filename):
        """Returns upload path for serial image. Preserves the original file extension."""
        import os as _os
        ext = _os.path.splitext(filename)[1].lower() or '.jpg'
        return f'serial_images_pistol/{instance.item_id}{ext}'
    serial_image = models.ImageField(upload_to=serial_image_upload_to, blank=True, null=True)
    # qr_code stores the QR data string (equal to item_id); qr_code_image is the rendered PNG.
    qr_code = models.CharField(max_length=100, unique=True, blank=False, editable=False)
    qr_code_image = models.ImageField(upload_to='qr_code_images_pistol', blank=True, null=True)
    # item_tag stores the generated item ID tag PNG (media/item_id_tags/<item_id>.png).
    item_tag = models.ImageField(upload_to='item_id_tags', blank=True, null=True)
    # -- Description and audit timestamps --------------------------------------
    description = models.TextField(blank=True, null=True)
    created = models.DateTimeField(blank=True, null=True)
    created_by = models.CharField(max_length=50, blank=True, null=True)
    updated = models.DateTimeField(blank=True, null=True)
    updated_by = models.CharField(max_length=50, blank=True, null=True)
    # -- Remarks ---------------------------------------------------------------
    remarks = models.TextField(blank=True, null=True)
    remarks_timestamp = models.DateTimeField(blank=True, null=True)
    remarks_updated_by = models.CharField(max_length=100, blank=True, null=True)
    # -- Condition and operational status -------------------------------------
    item_condition = models.CharField(max_length=20, default='Serviceable', choices=CONDITION_CHOICES)
    item_status = models.CharField(max_length=20, default='Available', choices=STATUS_CHOICES)
    # -- Assignment tracking (FK ? Personnel with SET_NULL) --------------------
    # C1: Converted from CharField to ForeignKey — DB-enforced referential integrity.
    # SET_NULL on Personnel delete clears the FK automatically (no orphaned string values).
    # Managed via set_assigned() only — do not modify directly.
    item_assigned_to = models.ForeignKey(
        'personnel.Personnel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pistols_assigned',
        help_text="Personnel this pistol is pre-assigned to. Set via set_assigned() only."
    )
    item_assigned_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    item_assigned_by = models.CharField(max_length=100, blank=True, null=True, default=None)
    # -- Issuance tracking (FK — DB-enforced referential integrity) ------------
    # item_issued_to is set ONLY by Transaction.save() via set_issued().
    # Direct admin edits to this field bypass business rules — use Transactions instead.
    item_issued_to = models.ForeignKey(
        'personnel.Personnel',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='pistols_issued',
        help_text="Personnel this pistol is currently issued to. Set via Transactions only."
    )
    item_issued_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    item_issued_by = models.CharField(max_length=100, blank=True, null=True, default=None)

    class Meta:
        unique_together = (('item_number', 'model'),)
        # G8 FIX: DB-level CHECK constraints for status and condition enum values.
        constraints = [
            models.CheckConstraint(
                condition=models.Q(item_status__in=[
                    'Issued', 'Available', 'Under Maintenance',
                    'For Turn In', 'Turned In', 'Decommissioned',
                ]),
                name='pistol_item_status_valid',
            ),
            models.CheckConstraint(
                condition=models.Q(item_condition__in=[
                    'Serviceable', 'Unserviceable', 'Lost', 'Tampered',
                ]),
                name='pistol_item_condition_valid',
            ),
        ]

    def get_item_type_display(self):
        return 'PISTOL'

    def clean(self):
        """Validate that item_number is provided and unique within the same pistol model."""
        from django.core.exceptions import ValidationError
        errors = {}
        if not self.item_number:
            errors['item_number'] = 'Item number is required. Auto-assignment is not allowed.'
        else:
            qs = Pistol.objects.filter(model=self.model, item_number=self.item_number)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                errors['item_number'] = f'Item number {self.item_number} is already used by another {self.model} pistol.'
        if errors:
            raise ValidationError(errors)
        super().clean()

    def save(self, *args, **kwargs):
        """
        Extended save() that handles auto-generation of identifiers and QR codes:
        - Generates item_id as 'IP-<model_code>-<serial_number>' on first save.
        - Sets qr_code equal to item_id.
        - Generates a QR code PNG image when item_id is new or changes.
        - Records created/updated timestamps and the acting username.
        - item_number must be set before save(); no auto-assignment is performed.
        Pass user=<request.user> as a keyword argument to capture created_by/updated_by.
        """
        from django.db import IntegrityError, transaction
        from utils.qr_generator import generate_qr_code_to_buffer
        from django.core.files.base import ContentFile
        user = kwargs.pop('user', None)
        # Clean up replaced serial_image: delete old file from storage when a new image
        # is uploaded for an existing record (Django does not auto-delete replaced files).
        update_fields = kwargs.get('update_fields')
        if self.pk and not update_fields:
            try:
                _old = Pistol.objects.get(pk=self.pk)
                old_name = _old.serial_image.name if _old.serial_image else None
                new_name = self.serial_image.name if self.serial_image else None
                if old_name and old_name != new_name:
                    try:
                        _old.serial_image.storage.delete(old_name)
                    except Exception:
                        pass
            except Pistol.DoesNotExist:
                pass
        # Track previous remarks to detect changes
        _prev_remarks = None
        if self.pk:
            try:
                _prev_remarks = Pistol.objects.values_list('remarks', flat=True).get(pk=self.pk)
            except Pistol.DoesNotExist:
                pass
        from django.core.exceptions import ValidationError as _VE
        if not self.item_number:
            raise _VE({'item_number': 'Item number is required. Auto-assignment is not allowed.'})
        for attempt in range(1):
            # Generate item_id from model abbreviation and serial number on creation
            if not self.item_id:
                # BUG-FIX: Use exact choice-string keys so codes match real model names.
                # Old code compared against truncated strings ('Glock', 'M1911') that
                # never appear in the model field — every pistol got a raw .upper() id
                # full of spaces.  This map covers all five PISTOL_MODELS entries.
                import re as _re
                _PISTOL_CODE_MAP = {
                    'Glock 17 9mm':           'GL17',
                    'M1911 Cal.45':           'M1911',
                    'Armscor Hi Cap Cal.45':  'ARMSCOR',
                    'RIA Hi Cap Cal.45':      'RIA',
                    'M1911 Customized Cal.45':'M1911C',
                }
                model_code = _PISTOL_CODE_MAP.get(self.model) or _re.sub(r'[^A-Z0-9]', '_', self.model.upper())
                code = f"IP-{model_code}-{self.serial_number}"
                object.__setattr__(self, 'item_id', code)
            # QR code string is always equal to item_id
            self.qr_code = self.item_id
            if not self.created:
                self.created = timezone.now()
            if user and not self.created_by:
                self.created_by = user.username if hasattr(user, 'username') else str(user)
            self.updated = timezone.now()
            if user:
                self.updated_by = user.username if hasattr(user, 'username') else str(user)
            # Auto-track remarks changes
            if self.remarks and self.remarks != _prev_remarks:
                self.remarks_timestamp = timezone.now()
                if user:
                    self.remarks_updated_by = user.username if hasattr(user, 'username') else str(user)
            # Regenerate QR code image if item_id changed or image is missing
            regenerate_qr = False
            if not self.qr_code_image or not self.qr_code_image.name:
                regenerate_qr = True
            elif self.pk:
                try:
                    old = Pistol.objects.get(pk=self.pk)
                    if getattr(self, 'item_id', None) != getattr(old, 'item_id', None):
                        regenerate_qr = True
                except Pistol.DoesNotExist:
                    regenerate_qr = True
            if regenerate_qr:
                buffer = generate_qr_code_to_buffer(self.qr_code)
                filename = f"{self.item_id}.png"
                self.qr_code_image.save(filename, ContentFile(buffer.read()), save=False)
            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                break
            except IntegrityError as e:
                raise
        # Auto-generate item tag PNG after the record is committed.
        # Runs on creation and whenever item_id (and therefore the QR) changes.
        if not self.item_tag or not self.item_tag.name or regenerate_qr:
            try:
                from utils.item_tag_generator import generate_item_tag
                generate_item_tag(self)
            except Exception as _exc:
                import logging as _log
                _log.getLogger(__name__).warning(
                    "Auto item-tag generation failed for Pistol %s: %s", self.item_id, _exc
                )
# --- Rifle -------------------------------------------------------------------


class Rifle(SmallArm):
    """
    Represents a single rifle unit in the armory inventory.
    Fields are listed first (primary key, attributes, media, audit, status, tracking),
    followed by Meta, then all methods.
    item_id for M4 Carbine DSAR-15 5.56mm rifles uses factory_qr as the primary ID
    (factory QR codes on M4s carry the PAF serial embedded in the barcode).
    For all other models, item_id is auto-generated as 'IR-<model_code>-<serial_number>'.
    Issued status is enforced through set_issued() only — never set item_status='Issued'
    directly via admin without going through a Withdrawal Transaction.
    """
    # N7: arm_type used by SmallArm shared methods.
    arm_type = 'rifle'
    # N7: arm_type used by SmallArm shared methods.
    arm_type = 'rifle'
    # -- Primary key and identification ----------------------------------------
    item_id = models.CharField(max_length=50, primary_key=True, unique=True, blank=False, editable=False)
    item_number = models.CharField(max_length=4, blank=False, help_text="Required. Unique number within the same rifle model (e.g. 0001). Must be entered manually.")
    property_number = models.CharField(max_length=50, blank=True, null=True, unique=True, help_text="Government / property custodian number assigned to this rifle. Leave blank if not yet assigned.")
    # -- Item attributes -------------------------------------------------------
    # C4: FK to Category — enables item classification with referential integrity.
    category = models.ForeignKey(
        'Category',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rifles',
        help_text="Optional category classification for this rifle (e.g., Small Arms)."
    )
    model = models.CharField(max_length=30, choices=RIFLE_MODELS)
    # factory_qr is only required for M4 Carbine DSAR-15 5.56mm; stores the factory barcode string.
    factory_qr = models.CharField(max_length=100, blank=True, null=True, help_text="Factory QR code (required for M4 Carbine DSAR-15 5.56mm only).")
    serial_number = models.CharField(max_length=50, unique=True, blank=False)
    # -- Media files -----------------------------------------------------------

    def serial_image_upload_to(instance, filename):
        """Returns upload path for serial image. Preserves the original file extension."""
        import os as _os
        ext = _os.path.splitext(filename)[1].lower() or '.jpg'
        return f'serial_images_rifle/{instance.item_id}{ext}'
    serial_image = models.ImageField(upload_to=serial_image_upload_to, blank=True, null=True)
    # qr_code stores the QR data string (equals item_id for M4, or factory_qr/item_id for others).
    qr_code = models.CharField(max_length=100, unique=True, blank=False, editable=False)
    qr_code_image = models.ImageField(upload_to='qr_code_images_rifle', blank=True, null=True)
    # item_tag stores the generated item ID tag PNG (media/item_id_tags/<item_id>.png).
    item_tag = models.ImageField(upload_to='item_id_tags', blank=True, null=True)
    # -- Description and audit timestamps --------------------------------------
    description = models.TextField(blank=True, null=True)
    created = models.DateTimeField(blank=True, null=True)
    created_by = models.CharField(max_length=50, blank=True, null=True)
    updated = models.DateTimeField(blank=True, null=True)
    updated_by = models.CharField(max_length=50, blank=True, null=True)
    # -- Remarks ---------------------------------------------------------------
    remarks = models.TextField(blank=True, null=True)
    remarks_timestamp = models.DateTimeField(blank=True, null=True)
    remarks_updated_by = models.CharField(max_length=100, blank=True, null=True)
    # -- Condition and operational status --------------------------------------
    item_condition = models.CharField(max_length=20, default='Serviceable', choices=CONDITION_CHOICES)
    item_status = models.CharField(max_length=20, default='Available', choices=STATUS_CHOICES)
    # -- Assignment tracking (FK ? Personnel with SET_NULL) --------------------
    # C1: Converted from CharField to ForeignKey — DB-enforced referential integrity.
    # SET_NULL on Personnel delete clears the FK automatically (no orphaned string values).
    # Managed via set_assigned() only — do not modify directly.
    item_assigned_to = models.ForeignKey(
        'personnel.Personnel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rifles_assigned',
        help_text="Personnel this rifle is pre-assigned to. Set via set_assigned() only."
    )
    item_assigned_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    item_assigned_by = models.CharField(max_length=100, blank=True, null=True, default=None)
    # -- Issuance tracking (FK — DB-enforced referential integrity) ------------
    # item_issued_to is set ONLY by Transaction.save() via set_issued().
    # Direct admin edits to this field bypass business rules — use Transactions instead.
    item_issued_to = models.ForeignKey(
        'personnel.Personnel',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='rifles_issued',
        help_text="Personnel this rifle is currently issued to. Set via Transactions only."
    )
    item_issued_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    item_issued_by = models.CharField(max_length=100, blank=True, null=True, default=None)

    class Meta:
        unique_together = (('item_number', 'model'),)
        # G8 FIX: DB-level CHECK constraints for status and condition enum values.
        constraints = [
            models.CheckConstraint(
                condition=models.Q(item_status__in=[
                    'Issued', 'Available', 'Under Maintenance',
                    'For Turn In', 'Turned In', 'Decommissioned',
                ]),
                name='rifle_item_status_valid',
            ),
            models.CheckConstraint(
                condition=models.Q(item_condition__in=[
                    'Serviceable', 'Unserviceable', 'Lost', 'Tampered',
                ]),
                name='rifle_item_condition_valid',
            ),
        ]

    def get_item_type_display(self):
        return 'RIFLE'
    # -- Validation ------------------------------------------------------------

    def clean(self):
        """M4 Carbine DSAR-15 5.56mm requires factory_qr; no other model should have it set.
        Also validates item_number uniqueness within the same rifle model.
        Common item_status / issued_to / assignment checks are delegated to super().clean().
        """
        from django.core.exceptions import ValidationError
        errors = {}
        if self.model == 'M4 Carbine DSAR-15 5.56mm':
            if not self.factory_qr:
                errors['factory_qr'] = 'Factory QR code is required for M4 Carbine DSAR-15 5.56mm model.'
        else:
            if self.factory_qr:
                errors['factory_qr'] = 'Factory QR code should only be set for M4 Carbine DSAR-15 5.56mm model.'
        if not self.item_number:
            errors['item_number'] = 'Item number is required. Auto-assignment is not allowed.'
        else:
            qs = Rifle.objects.filter(model=self.model, item_number=self.item_number)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                errors['item_number'] = f'Item number {self.item_number} is already used by another {self.model} rifle.'
        if errors:
            raise ValidationError(errors)
        super().clean()
    # -- Save ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        """
        Extended save() that handles auto-generation of identifiers and QR codes:
        - For M4 Carbine DSAR-15 5.56mm: uses factory_qr as item_id and auto-extracts
          serial_number and description from the factory QR string (PAF<serial> pattern).
        - For all other models: generates item_id as 'IR-<model_code>-<serial_number>'.
        - Sets qr_code = item_id (M4) or factory_qr / item_id (others).
        - Generates a QR code PNG image on creation or when qr_code changes.
        - Records created/updated timestamps and the acting username.
        - item_number must be set before save(); no auto-assignment is performed.
        Pass user=<request.user> as a keyword argument to capture created_by/updated_by.
        """
        from django.db import IntegrityError, transaction
        from utils.qr_generator import generate_qr_code_to_buffer
        from django.core.files.base import ContentFile
        import re
        user = kwargs.pop('user', None)
        # Clean up replaced serial_image: delete old file from storage when a new image
        # is uploaded for an existing record (Django does not auto-delete replaced files).
        update_fields = kwargs.get('update_fields')
        if self.pk and not update_fields:
            try:
                _old = Rifle.objects.get(pk=self.pk)
                old_name = _old.serial_image.name if _old.serial_image else None
                new_name = self.serial_image.name if self.serial_image else None
                if old_name and old_name != new_name:
                    try:
                        _old.serial_image.storage.delete(old_name)
                    except Exception:
                        pass
            except Rifle.DoesNotExist:
                pass
        # Track previous remarks to detect changes
        _prev_remarks = None
        if self.pk:
            try:
                _prev_remarks = Rifle.objects.values_list('remarks', flat=True).get(pk=self.pk)
            except Rifle.DoesNotExist:
                pass
        # Auto-extract serial_number and description from factory_qr for M4 rifles
        if self.factory_qr and (not self.serial_number or not self.description):
            # BUG-FIX: was PAF\d{8} (8 digits) but real serials can be 10+ digits.
            # Use PAF\d+ to capture any length.
            match = re.search(r'(PAF\d+)', self.factory_qr)
            if match:
                serial = match.group(1)
                self.serial_number = self.serial_number or serial
                before = self.factory_qr.split(serial)[0]
                after = self.factory_qr.split(serial)[1]
                self.description = self.description or (before + after)
        from django.core.exceptions import ValidationError as _VE
        if not self.item_number:
            raise _VE({'item_number': 'Item number is required. Auto-assignment is not allowed.'})
        for attempt in range(1):
            # M4 uses factory_qr as item_id; all others use IR-<code>-<serial>
            if self.model == 'M4 Carbine DSAR-15 5.56mm' and self.factory_qr:
                object.__setattr__(self, 'item_id', self.factory_qr)
            elif not self.item_id:
                # BUG-FIX: Old map used short keys ('M4','M16') that never matched the
                # actual full model strings ('M4 Carbine DSAR-15 5.56mm', etc.) —
                # every non-M4 rifle got a raw .upper() id full of spaces/special chars.
                import re as _re
                _RIFLE_CODE_MAP = {
                    'M4 Carbine DSAR-15 5.56mm':     'M4',
                    'M4 14.5" DGIS EMTAN 5.56mm':    'M4E',
                    'M16A1 Rifle 5.56mm':             'M16',
                    'M14 Rifle 7.62mm':               'M14',
                    'M653 Carbine 5.56mm':            'M653',
                }
                model_code = _RIFLE_CODE_MAP.get(self.model) or _re.sub(r'[^A-Z0-9]', '_', self.model.upper())
                code = f"IR-{model_code}-{self.serial_number}"
                object.__setattr__(self, 'item_id', code)
            # QR code string: M4 ? item_id; others ? factory_qr if available, else item_id
            if self.model == 'M4 Carbine DSAR-15 5.56mm':
                self.qr_code = self.item_id
            else:
                self.qr_code = self.factory_qr or self.item_id
            if not self.created:
                self.created = timezone.now()
            if user and not self.created_by:
                self.created_by = user.username if hasattr(user, 'username') else str(user)
            self.updated = timezone.now()
            if user:
                self.updated_by = user.username if hasattr(user, 'username') else str(user)
            # Auto-track remarks changes
            if self.remarks and self.remarks != _prev_remarks:
                self.remarks_timestamp = timezone.now()
                if user:
                    self.remarks_updated_by = user.username if hasattr(user, 'username') else str(user)
            # Regenerate QR code image if qr_code changed or image is missing
            regenerate_qr = False
            if not self.qr_code_image or not self.qr_code_image.name:
                regenerate_qr = True
            elif self.pk:
                try:
                    old = Rifle.objects.get(pk=self.pk)
                    if getattr(self, 'qr_code', None) != getattr(old, 'qr_code', None):
                        regenerate_qr = True
                except Rifle.DoesNotExist:
                    regenerate_qr = True
            if regenerate_qr:
                buffer = generate_qr_code_to_buffer(self.qr_code)
                filename = f"{self.item_id}.png"
                self.qr_code_image.save(filename, ContentFile(buffer.read()), save=False)
            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                break
            except IntegrityError as e:
                raise
        # Auto-generate item tag PNG after the record is committed.
        # Runs on creation and whenever qr_code (and therefore item_id) changes.
        if not self.item_tag or not self.item_tag.name or regenerate_qr:
            try:
                from utils.item_tag_generator import generate_item_tag
                generate_item_tag(self)
            except Exception as _exc:
                import logging as _log
                _log.getLogger(__name__).warning(
                    "Auto item-tag generation failed for Rifle %s: %s", self.item_id, _exc
                )
# --- Magazine ----------------------------------------------------------------


class Magazine(models.Model):
    """
    Inventory pool model for pistol and rifle magazines.
    Each record represents a weapon_type + type pool:
      - Pistol: weapon_type='Pistol', type='Pistol Standard'
      - Rifle Short: weapon_type='Rifle', type='Short' (20-rounds)
      - Rifle Long:  weapon_type='Rifle', type='Long'  (30-rounds)
    quantity reflects total available stock; transactions adjust it via adjust_quantity().
    Use can_be_withdrawn() before any Transaction withdrawal to validate available stock.
    """
    # -- Fields ----------------------------------------------------------------
    # C4: FK to Category — enables item classification with referential integrity.
    category = models.ForeignKey(
        'Category',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='magazines',
        help_text="Optional category classification for this magazine pool."
    )
    # weapon_type distinguishes pistol pools from rifle pools.
    # Pistol pools: type='Pistol Standard'  (max 4 per withdrawal per spec)
    # Rifle pools:  type='Short' or 'Long'
    weapon_type = models.CharField(
        max_length=10,
        choices=[('Pistol', 'Pistol'), ('Rifle', 'Rifle')],
        default='Rifle',
        help_text="Whether this magazine pool is for pistols or rifles. Auto-set by save() from type."
    )
    type = models.CharField(max_length=30, choices=ALL_MAGAZINE_TYPES)
    # capacity is auto-set by save(): Pistol Standard ? 'Standard', Short ? '20-rounds', Long ? '30-rounds'.
    capacity = models.CharField(max_length=10, blank=True, editable=True)
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        blank=False, null=False,
        help_text="Total number of magazine units currently in stock."
    )
    description = models.TextField(blank=True, null=True)
    created = models.DateTimeField(blank=True, null=True)
    created_by = models.CharField(max_length=50, blank=True, null=True)
    updated = models.DateTimeField(blank=True, null=True)
    updated_by = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = 'Magazine'
        verbose_name_plural = 'Magazines'
        # G8 FIX: DB-level quantity floor.
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0),
                name='magazine_quantity_nonneg',
            ),
        ]
    # -- String representation -------------------------------------------------

    def __str__(self):
        return f"{self.type} ({self.capacity})"
    # -- Business rule queries -------------------------------------------------

    def can_be_withdrawn(self, quantity):
        """
        Returns (True, None) if the requested quantity is available.
        Returns (False, reason_string) if quantity is invalid or exceeds stock.
        Always call this before creating a withdrawal Transaction for this item.
        """
        if not quantity or quantity <= 0:
            return False, "Withdrawal quantity must be greater than 0."
        if self.quantity < quantity:
            return False, f"Insufficient magazine quantity. Available: {self.quantity}, requested: {quantity}."
        return True, None
    # -- Quantity mutation -----------------------------------------------------

    def adjust_quantity(self, delta):
        """
        Atomically adjusts the magazine stock quantity at the DB level.
        Pass a negative delta for withdrawal, positive for return.
        Uses Greatest(0, quantity + delta) to floor at 0 without a Python-level
        read — eliminates the race condition that could cause negative stock under
        concurrent transactions. (REC-02)
        Called from Transaction.save() — do not call directly in user code.
        """
        from django.db.models import F
        from django.db.models.functions import Greatest
        Magazine.objects.filter(pk=self.pk).update(
            quantity=Greatest(0, F('quantity') + delta)
        )
        self.refresh_from_db(fields=['quantity'])
    # -- Save -----------------------------------------------------------------

    def save(self, *args, **kwargs):
        """
        Auto-sets weapon_type and capacity from type:
          Pistol Standard ? weapon_type='Pistol', capacity='Standard'
          Short           ? weapon_type='Rifle',  capacity='20-rounds'
          Long            ? weapon_type='Rifle',  capacity='30-rounds'
        Records created/updated timestamps and the acting username.
        """
        user = kwargs.pop('user', None)
        # Derive weapon_type and capacity label from magazine type
        if self.type == 'Pistol Standard':
            self.weapon_type = 'Pistol'
            self.capacity = 'Standard'
        elif self.type == 'Short':
            self.weapon_type = 'Rifle'
            self.capacity = '20-rounds'
        elif self.type == 'Long':
            self.weapon_type = 'Rifle'
            self.capacity = '30-rounds'
        if not self.created:
            self.created = timezone.now()
            if user and not self.created_by:
                self.created_by = user.username
        self.updated = timezone.now()
        if user:
            self.updated_by = user.username
        super().save(*args, **kwargs)
# --- Ammunition --------------------------------------------------------------


class Ammunition(models.Model):
    """
    Inventory pool model for ammunition lots.
    Each record is a lot of a specific caliber/type. quantity reflects total available rounds.
    Transactions adjust quantity via adjust_quantity().
    Use can_be_withdrawn() before any Transaction withdrawal to validate available stock.
    """
    # -- Fields ----------------------------------------------------------------
    # C4: FK to Category — enables item classification with referential integrity.
    category = models.ForeignKey(
        'Category',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ammunition',
        help_text="Optional category classification for this ammunition lot."
    )
    type = models.CharField(max_length=30, choices=AMMUNITION_TYPES)
    lot_number = models.CharField(max_length=50, unique=True, help_text="Lot/batch number for this ammunition consignment.")
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        blank=False, null=False,
        help_text="Total number of rounds currently in stock."
    )
    description = models.TextField(blank=True, null=True)
    created = models.DateTimeField(blank=True, null=True)
    created_by = models.CharField(max_length=50, blank=True, null=True)
    updated = models.DateTimeField(blank=True, null=True)
    updated_by = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = 'Ammunition'
        verbose_name_plural = 'Ammunition'
        # G8 FIX: DB-level quantity floor.
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0),
                name='ammunition_quantity_nonneg',
            ),
        ]
    # -- String representation -------------------------------------------------

    def __str__(self):
        # Use stable fields (type + lot_number) so str(ammo) never changes after
        # quantity adjustments — required for consistent can_return_ammunition() comparisons.
        return f"{self.type} — Lot: {self.lot_number}"
    # -- Business rule queries -------------------------------------------------

    def can_be_withdrawn(self, quantity):
        """
        Returns (True, None) if the requested round count is available.
        Returns (False, reason_string) if quantity is invalid or exceeds stock.
        Always call this before creating a withdrawal Transaction for this item.
        """
        if not quantity or quantity <= 0:
            return False, "Withdrawal quantity must be greater than 0."
        if self.quantity < quantity:
            return False, f"Insufficient ammunition quantity. Available: {self.quantity}, requested: {quantity}."
        return True, None
    # -- Quantity mutation -----------------------------------------------------

    def adjust_quantity(self, delta):
        """
        Atomically adjusts the ammunition stock quantity at the DB level.
        Pass a negative delta for withdrawal, positive for return.
        Uses Greatest(0, quantity + delta) to floor at 0 without a Python-level
        read — eliminates the race condition that could cause negative stock under
        concurrent transactions. (REC-02)
        Called from Transaction.save() — do not call directly in user code.
        """
        from django.db.models import F
        from django.db.models.functions import Greatest
        Ammunition.objects.filter(pk=self.pk).update(
            quantity=Greatest(0, F('quantity') + delta)
        )
        self.refresh_from_db(fields=['quantity'])
    # -- Save -----------------------------------------------------------------

    def save(self, *args, **kwargs):
        """
        Records created/updated timestamps and the acting username.
        """
        user = kwargs.pop('user', None)
        if not self.created:
            self.created = timezone.now()
            if user and not self.created_by:
                self.created_by = user.username
        self.updated = timezone.now()
        if user:
            self.updated_by = user.username
        super().save(*args, **kwargs)
# --- Accessory ---------------------------------------------------------------


class Accessory(models.Model):
    """
    Inventory pool model for accessories (holsters, slings, pouches, bandoleers, etc.).
    Each record is a distinct accessory type with a running quantity.
    Withdrawals reduce and returns increase quantity through adjust_quantity().
    Use can_be_withdrawn() before any Transaction withdrawal to validate available stock.
    NOTE: The former withdraw() and return_accessory() methods have been removed.
    All accessory quantity movements must go through Transaction.save(), which calls
    adjust_quantity() directly after validating via can_be_withdrawn().
    """
    # -- Fields ----------------------------------------------------------------
    # C4: FK to Category — enables item classification with referential integrity.
    category = models.ForeignKey(
        'Category',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accessories',
        help_text="Optional category classification for this accessory pool."
    )
    type = models.CharField(max_length=50, choices=ACCESSORY_TYPES)
    quantity = models.PositiveIntegerField(
        help_text="Total number of units currently in stock."
    )
    description = models.TextField(blank=True, null=True)
    created = models.DateTimeField(blank=True, null=True)
    created_by = models.CharField(max_length=50, blank=True, null=True)
    updated = models.DateTimeField(blank=True, null=True)
    updated_by = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = 'Accessory'
        verbose_name_plural = 'Accessories'
        # G8 FIX: DB-level quantity floor.
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0),
                name='accessory_quantity_nonneg',
            ),
        ]
    # -- String representation -------------------------------------------------

    def __str__(self):
        return self.type
    # -- Business rule queries -------------------------------------------------

    def can_be_withdrawn(self, quantity=1):
        """
        Returns (True, None) if sufficient accessories are available for withdrawal.
        Returns (False, reason_string) if the requested quantity exceeds stock.
        Always call this before creating a withdrawal Transaction for this item.
        """
        if not quantity or quantity <= 0:
            return False, "Withdrawal quantity must be greater than 0."
        if self.quantity < quantity:
            return False, f"Insufficient accessory quantity. Available: {self.quantity}, requested: {quantity}."
        return True, None
    # -- Quantity mutation -----------------------------------------------------

    def adjust_quantity(self, delta):
        """
        Atomically adjusts the accessory stock quantity at the DB level.
        Pass a negative delta for withdrawal, positive for return.
        Uses Greatest(0, quantity + delta) to floor at 0 without a Python-level
        read — eliminates the race condition that could cause negative stock under
        concurrent transactions. (REC-02)
        Called from Transaction.save() — do not call directly in user code.
        """
        from django.db.models import F
        from django.db.models.functions import Greatest
        Accessory.objects.filter(pk=self.pk).update(
            quantity=Greatest(0, F('quantity') + delta)
        )
        self.refresh_from_db(fields=['quantity'])
    # -- Save -----------------------------------------------------------------

    def save(self, *args, **kwargs):
        """
        Records created/updated timestamps and the acting username.
        Pass user=<request.user> as a keyword argument to capture created_by/updated_by.
        """
        user = kwargs.pop('user', None)
        if not self.created:
            self.created = timezone.now()
            if user and not self.created_by:
                self.created_by = user.username
        self.updated = timezone.now()
        if user:
            self.updated_by = user.username
        super().save(*args, **kwargs)
# --- Serial Image Phone Capture (temporary session) ------------------------


class SerialImageCapture(models.Model):
    """
    Temporary session holding a serial image captured via the armorer's phone.
    Created when the admin clicks "Capture via Phone" on the pistol/rifle form.
    The phone scans the QR code, takes a photo, and uploads it here via
    serial_capture_upload.  The admin browser polls until the image arrives
    and then injects it into the file input so the crop modal opens as normal.
    Records older than 30 minutes are purged automatically by serial_capture_init.
    """
    token      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image      = models.ImageField(upload_to='serial_capture_temp/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Serial Image Capture Session'
# Expose Inventory_Analytics to Django's app registry so it gets a DB table.
from .inventory_analytics_model import Inventory_Analytics, AnalyticsSnapshot  # noqa: E402,F401
# Expose FirearmDiscrepancy to Django's app registry.
from .pistol_rifle_discrepancy_model import FirearmDiscrepancy  # noqa: E402,F401
