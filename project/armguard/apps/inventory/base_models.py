"""
Base models for inventory items (Pistol and Rifle).

This module provides a shared abstract base class for SmallArm items
to reduce code duplication between Pistol and Rifle models.

N7 FIX: Abstract base model applied to Pistol and Rifle.
Subclasses must set  arm_type = 'pistol'  or  arm_type = 'rifle'.
Field definitions that differ between Pistol and Rifle are kept on the
concrete classes (e.g. model choices, qr_code_image upload folder) while
all shared methods are defined here once.
"""

from django.db import models
from django.utils import timezone


class SmallArm(models.Model):
    """
    Abstract base model for small arms (Pistol and Rifle).

    Provides all shared field definitions and every business-logic method so
    that concrete subclasses only need to declare model-specific fields and
    their auto-save() logic.  Subclasses MUST set the class attribute:

        arm_type = 'pistol'  |  'rifle'
    """

    arm_type = ''  # Overridden in every concrete subclass

    # -- Primary key and identification ----------------------------------------
    item_id = models.CharField(max_length=50, primary_key=True, unique=True, blank=False, editable=False)
    item_number = models.CharField(max_length=4, blank=True, help_text="Sequential number within the same model. Auto-assigned.")

    # -- Item attributes -------------------------------------------------------
    # Concrete subclasses keep their own `category` FK with an explicit
    # related_name ('pistols' / 'rifles') so this base definition is a fallback
    # only (it is overridden by Pistol and Rifle).
    category = models.ForeignKey(
        'Category',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)ss',
        help_text="Optional category classification for this item (e.g., Small Arms)."
    )
    model = models.CharField(max_length=30)  # Overridden in subclass with choices
    serial_number = models.CharField(max_length=50, unique=True, blank=False)

    # -- Media files -----------------------------------------------------------
    # qr_code_image upload folder differs per arm type; concrete subclasses keep
    # their own definition.  serial_image upload_to is a callable that works for
    # both since it reads self.arm_type at runtime.
    def serial_image_upload_to(self, filename):
        import os as _os
        ext = _os.path.splitext(filename)[1].lower() or '.jpg'
        return f'serial_images_{self.arm_type}/{self.item_id}{ext}'

    serial_image = models.ImageField(upload_to=serial_image_upload_to, blank=True, null=True)
    qr_code = models.CharField(max_length=100, unique=True, blank=False, editable=False)
    item_tag = models.ImageField(upload_to='item_id_tags', blank=True, null=True)

    # -- Description and audit timestamps --------------------------------------
    description = models.TextField(blank=True, null=True)
    created = models.DateTimeField(blank=True, null=True)
    created_by = models.CharField(max_length=50, blank=True, null=True)
    updated = models.DateTimeField(blank=True, null=True)
    updated_by = models.CharField(max_length=50, blank=True, null=True)

    # -- Condition and operational status --------------------------------------
    item_condition = models.CharField(max_length=20, default='Serviceable')
    item_status = models.CharField(max_length=20, default='Available')

    # -- Assignment tracking ---------------------------------------------------
    # Concrete subclasses keep explicit related_names ('pistols_assigned' /
    # 'rifles_assigned') that override this base definition.
    item_assigned_to = models.ForeignKey(
        'personnel.Personnel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)ss_assigned',
        help_text="Personnel this item is pre-assigned to. Set via set_assigned() only."
    )
    item_assigned_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    item_assigned_by = models.CharField(max_length=100, blank=True, null=True, default=None)

    # -- Issuance tracking ----------------------------------------------------
    # Concrete subclasses keep explicit related_names ('pistols_issued' /
    # 'rifles_issued') that override this base definition.
    item_issued_to = models.ForeignKey(
        'personnel.Personnel',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='%(class)ss_issued',
        help_text="Personnel this item is currently issued to. Set via Transactions only."
    )
    item_issued_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    item_issued_by = models.CharField(max_length=100, blank=True, null=True, default=None)

    class Meta:
        abstract = True

    # -- Item-tag generator compatibility properties ---------------------------
    @property
    def id(self):
        return self.item_id

    @property
    def serial(self):
        return self.serial_number

    @property
    def item_type(self):
        return self.arm_type

    # -- Validation -----------------------------------------------------------
    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()

        if self.item_status == 'Issued' and not self.item_issued_to_id:
            raise ValidationError({
                'item_status': (
                    f'Cannot mark {self.arm_type} as Issued without specifying who it is issued to. '
                    'Use the Transactions module.'
                )
            })

        if self.item_status == 'Available' and self.item_issued_to_id:
            self.item_issued_to = None
            self.item_issued_timestamp = None
            self.item_issued_by = None

        if self.item_assigned_to_id and self.item_issued_to_id and self.item_assigned_to_id != self.item_issued_to_id:
            raise ValidationError({
                'item_assigned_to': (
                    f"Assignment ({self.item_assigned_to_id}) and issuance ({self.item_issued_to_id}) "
                    "records point to different personnel. Clear the assignment first or correct the issuance."
                )
            })

    # -- State mutations -------------------------------------------------------
    def set_issued(self, personnel_id, timestamp, issued_by):
        """Updates issued tracking fields."""
        self.item_issued_to_id = personnel_id
        self.item_issued_timestamp = timestamp
        self.item_issued_by = issued_by
        self.item_status = 'Issued' if personnel_id else 'Available'
        self.save(update_fields=[
            "item_issued_to_id", "item_issued_timestamp", 
            "item_issued_by", "item_status"
        ])

    def set_assigned(self, personnel_id, timestamp, assigned_by):
        """Updates assignment tracking fields."""
        self.item_assigned_to_id = personnel_id
        self.item_assigned_timestamp = timestamp
        self.item_assigned_by = assigned_by
        self.save(update_fields=[
            "item_assigned_to_id", "item_assigned_timestamp", "item_assigned_by"
        ])

    # -- Business rule queries ------------------------------------------------
    def can_be_withdrawn(self):
        """Returns (True, None) if eligible for withdrawal."""
        if self.item_status == 'Issued':
            return False, (
                f"{self.arm_type.title()} {self.item_id} is already issued to "
                f"{self.item_issued_to_id} and must be returned first."
            )
        if self.item_status in ('Under Maintenance', 'For Turn In', 'Turned In', 'Decommissioned'):
            return False, (
                f"{self.arm_type.title()} {self.item_id} cannot be withdrawn "
                f"— current status: {self.item_status}."
            )
        return True, None

    def can_be_returned(self, personnel_id=None):
        """Returns (True, None) if eligible for return."""
        if self.item_status != 'Issued':
            return False, (
                f"{self.arm_type.title()} {self.item_id} is not currently issued "
                "and cannot be returned."
            )
        if personnel_id and self.item_issued_to_id and self.item_issued_to_id != personnel_id:
            return False, (
                f"{self.arm_type.title()} {self.item_id} was issued to "
                f"{self.item_issued_to_id}, not to {personnel_id}."
            )
        return True, None

    # -- Delete ---------------------------------------------------------------
    def delete(self, *args, **kwargs):
        """Deletes associated media files before removing the DB record."""
        # QR code image
        if self.qr_code_image and self.qr_code_image.name:
            try:
                self.qr_code_image.storage.delete(self.qr_code_image.name)
            except Exception:
                pass
        # Serial image
        if self.serial_image and self.serial_image.name:
            try:
                self.serial_image.storage.delete(self.serial_image.name)
            except Exception:
                pass
        # Item tag PNG
        if self.item_tag and self.item_tag.name:
            try:
                self.item_tag.storage.delete(self.item_tag.name)
            except Exception:
                pass
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.model} ({self.serial_number})"

