from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.apps import apps
import re
from django.utils import timezone
from django.core.files.base import ContentFile
from django.core.validators import RegexValidator
from utils.qr_generator import generate_qr_code_to_buffer

class Personnel(models.Model):
    duty_type = models.CharField(max_length=50, blank=True, null=True, help_text="Duty type for this personnel (optional)")
    # Personnel model for Air Guard personnel
    def get_display_str(self):
        return (
            f"{self.rank} {self.first_name} {self.middle_initial} {self.last_name} {self.AFSN} PAF\n"
            f"Personnel ID: {self.Personnel_ID}"
        )
    # Rank choices - Enlisted
    RANKS_ENLISTED = [
        ('AM', 'Airman'),
        ('AW', 'Airwoman'),
        ('A2C', 'Airman 2nd Class'),
        ('AW2C', 'Airwoman 2nd Class'),
        ('A1C', 'Airman 1st Class'),
        ('AW1C', 'Airwoman 1st Class'),
        ('SGT', 'Sergeant'),
        ('SSGT', 'Staff Sergeant'),
        ('TSGT', 'Technical Sergeant'),
        ('MSGT', 'Master Sergeant'),
        ('SMSGT', 'Senior Master Sergeant'),
        ('CMSGT', 'Chief Master Sergeant'),
    ]

    # Rank choices - Officers
    RANKS_OFFICER = [
        ('2LT', 'Second Lieutenant'),
        ('1LT', 'First Lieutenant'),
        ('CPT', 'Captain'),
        ('MAJ', 'Major'),
        ('LTCOL', 'Lieutenant Colonel'),
        ('COL', 'Colonel'),
        ('BGEN', 'Brigadier General'),
        ('MGEN', 'Major General'),
        ('LTGEN', 'Lieutenant General'),
        ('GEN', 'General'),
    ]

    ALL_RANKS = RANKS_ENLISTED + RANKS_OFFICER

    # Group choices
    GROUP_CHOICES = [
        ('HAS', 'HAS'),
        ('951st', '951st'),
        ('952nd', '952nd'),
        ('953rd', '953rd'),
    ]

    # Status choices
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Inactive', 'Inactive'),
    ]

    # Personnel fields
    Personnel_ID = models.CharField(primary_key=True, max_length=50, unique=True, blank=False, editable=False)
    rank = models.CharField(max_length=20, choices=ALL_RANKS)
    first_name = models.CharField(max_length=20)
    last_name = models.CharField(max_length=20)
    middle_initial = models.CharField(max_length=1)
    AFSN = models.CharField(max_length=10, unique=True)
    group = models.CharField(max_length=10, choices=GROUP_CHOICES)
    squadron = models.CharField(max_length=20)
    tel = models.CharField(
        max_length=11,
        unique=True,
        blank=True,
        null=True,
        validators=[RegexValidator(r'^\d+$', 'Enter numbers only.')],
        help_text="Contact telephone number (digits only, max 11 characters). Required for TR issuance."
    )
    personnel_image = models.ImageField(upload_to='personnel_images/', blank=True, null=True)
    qr_code = models.CharField(max_length=100, unique=True, blank=True)
    qr_code_image = models.ImageField(upload_to='qr_code_images_personnel/', blank=True, null=True)
    # Changed: removed auto_now_add and auto_now to allow nullable fields
    created = models.DateTimeField(blank=True, null=True)
    created_by = models.CharField(max_length=50, blank=True, null=True)
    updated = models.DateTimeField(blank=True, null=True)
    updated_by = models.CharField(max_length=50, blank=True, null=True)
    # Status Active, Inactive
    status = models.CharField(max_length=10, default='Active', choices=STATUS_CHOICES)
    # User foreign key
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    # Primary weapon and item tracking fields
    rifle_item_assigned = models.CharField(max_length=100, blank=True, null=True, default=None)  # Store assigned item name or ID
    rifle_item_assigned_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    rifle_item_assigned_by = models.CharField(max_length=100, blank=True, null=True, default=None)
    rifle_item_issued = models.CharField(max_length=100, blank=True, null=True, default=None)  # Store issued item name or ID
    rifle_item_issued_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    rifle_item_issued_by = models.CharField(max_length=100, blank=True, null=True, default=None)
    # Secondary weapon and item tracking fields
    pistol_item_assigned = models.CharField(max_length=100, blank=True, null=True, default=None)  # Store assigned item name or ID
    pistol_item_assigned_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    pistol_item_assigned_by = models.CharField(max_length=100, blank=True, null=True, default=None)
    pistol_item_issued = models.CharField(max_length=100, blank=True, null=True, default=None)  # Store issued item name or ID
    pistol_item_issued_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    pistol_item_issued_by = models.CharField(max_length=100, blank=True, null=True, default=None)
    # Magazine tracking fields
    magazine_item_assigned = models.CharField(max_length=100, blank=True, null=True, default=None)
    magazine_item_assigned_quantity = models.PositiveIntegerField(blank=True, null=True, default=None)
    magazine_item_assigned_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    magazine_item_assigned_by = models.CharField(max_length=100, blank=True, null=True, default=None)
    # Deprecated: use pistol_magazine_item_issued / rifle_magazine_item_issued instead.
    # Kept for backwards compatibility until data is migrated. (REC-05)
    magazine_item_issued = models.CharField(max_length=100, blank=True, null=True, default=None)
    magazine_item_issued_quantity = models.PositiveIntegerField(blank=True, null=True, default=None)
    magazine_item_issued_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    magazine_item_issued_by = models.CharField(max_length=100, blank=True, null=True, default=None)
    # REC-05: Separate pistol and rifle magazine tracking to prevent overwrite when both
    # are issued in a single transaction (the old shared field was last-write-wins).
    pistol_magazine_item_issued = models.CharField(max_length=100, blank=True, null=True, default=None)
    pistol_magazine_item_issued_quantity = models.PositiveIntegerField(blank=True, null=True, default=None)
    pistol_magazine_item_issued_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    pistol_magazine_item_issued_by = models.CharField(max_length=100, blank=True, null=True, default=None)
    rifle_magazine_item_issued = models.CharField(max_length=100, blank=True, null=True, default=None)
    rifle_magazine_item_issued_quantity = models.PositiveIntegerField(blank=True, null=True, default=None)
    rifle_magazine_item_issued_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    rifle_magazine_item_issued_by = models.CharField(max_length=100, blank=True, null=True, default=None)
    # Ammunition tracking fields
    ammunition_item_assigned = models.CharField(max_length=100, blank=True, null=True, default=None)
    ammunition_item_assigned_quantity = models.PositiveIntegerField(blank=True, null=True, default=None)
    ammunition_item_assigned_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    ammunition_item_assigned_by = models.CharField(max_length=100, blank=True, null=True, default=None)
    ammunition_item_issued = models.CharField(max_length=100, blank=True, null=True, default=None)
    ammunition_item_issued_quantity = models.PositiveIntegerField(blank=True, null=True, default=None)
    ammunition_item_issued_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    ammunition_item_issued_by = models.CharField(max_length=100, blank=True, null=True, default=None)
    # REC-06: Separate pistol and rifle ammunition tracking — prevents the second
    # set_issued('ammunition', ...) call from silently overwriting the first when
    # both pistol_ammunition and rifle_ammunition are issued in the same transaction.
    pistol_ammunition_item_issued = models.CharField(max_length=100, blank=True, null=True, default=None)
    pistol_ammunition_item_issued_quantity = models.PositiveIntegerField(blank=True, null=True, default=None)
    pistol_ammunition_item_issued_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    pistol_ammunition_item_issued_by = models.CharField(max_length=100, blank=True, null=True, default=None)
    rifle_ammunition_item_issued = models.CharField(max_length=100, blank=True, null=True, default=None)
    rifle_ammunition_item_issued_quantity = models.PositiveIntegerField(blank=True, null=True, default=None)
    rifle_ammunition_item_issued_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    rifle_ammunition_item_issued_by = models.CharField(max_length=100, blank=True, null=True, default=None)
    # Accessory tracking — per type (Pistol Holster, Pistol Magazine Pouch, Rifle Sling, Bandoleer)
    pistol_holster_issued = models.CharField(max_length=100, blank=True, null=True, default=None)
    pistol_holster_issued_quantity = models.PositiveIntegerField(blank=True, null=True, default=None)
    pistol_holster_issued_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    pistol_holster_issued_by = models.CharField(max_length=100, blank=True, null=True, default=None)
    magazine_pouch_issued = models.CharField(max_length=100, blank=True, null=True, default=None)
    magazine_pouch_issued_quantity = models.PositiveIntegerField(blank=True, null=True, default=None)
    magazine_pouch_issued_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    magazine_pouch_issued_by = models.CharField(max_length=100, blank=True, null=True, default=None)
    rifle_sling_issued = models.CharField(max_length=100, blank=True, null=True, default=None)
    rifle_sling_issued_quantity = models.PositiveIntegerField(blank=True, null=True, default=None)
    rifle_sling_issued_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    rifle_sling_issued_by = models.CharField(max_length=100, blank=True, null=True, default=None)
    bandoleer_issued = models.CharField(max_length=100, blank=True, null=True, default=None)
    bandoleer_issued_quantity = models.PositiveIntegerField(blank=True, null=True, default=None)
    bandoleer_issued_timestamp = models.DateTimeField(blank=True, null=True, default=None)
    bandoleer_issued_by = models.CharField(max_length=100, blank=True, null=True, default=None)

    # Methods for issuance transaction synchronization
    def set_issued(self, item_type, item_name, timestamp, issued_by, quantity=None):
        """
        Syncs issued-item tracking fields for the given item type.

        Called from Transaction.save() whenever a Withdrawal or Return is saved.
        Pass item_name=None and timestamp=None to CLEAR issued fields (on Return).

        Supported item_type values:
          'rifle'       — updates rifle_item_issued + timestamp + by
          'pistol'      — updates pistol_item_issued + timestamp + by
          'magazine'    — updates magazine_item_issued + quantity + timestamp + by
          'ammunition'  — updates ammunition_item_issued + quantity + timestamp + by
          'accessory'   — updates accessory_item_issued + quantity + timestamp + by

        quantity param is required for magazine, ammunition, and accessory types.
        Uses update_fields for a targeted DB write (no full-record rewrite).
        """
        if item_type == 'rifle':
            self.rifle_item_issued = item_name
            self.rifle_item_issued_timestamp = timestamp
            self.rifle_item_issued_by = issued_by
            self.save(update_fields=["rifle_item_issued", "rifle_item_issued_timestamp", "rifle_item_issued_by"])
        elif item_type == 'pistol':
            self.pistol_item_issued = item_name
            self.pistol_item_issued_timestamp = timestamp
            self.pistol_item_issued_by = issued_by
            self.save(update_fields=["pistol_item_issued", "pistol_item_issued_timestamp", "pistol_item_issued_by"])
        elif item_type == 'magazine':
            self.magazine_item_issued = item_name
            self.magazine_item_issued_quantity = quantity
            self.magazine_item_issued_timestamp = timestamp
            self.magazine_item_issued_by = issued_by
            self.save(update_fields=[
                "magazine_item_issued", "magazine_item_issued_quantity",
                "magazine_item_issued_timestamp", "magazine_item_issued_by",
            ])
        elif item_type == 'pistol_magazine':
            # REC-05: Dedicated pistol magazine tracking field.
            self.pistol_magazine_item_issued = item_name
            self.pistol_magazine_item_issued_quantity = quantity
            self.pistol_magazine_item_issued_timestamp = timestamp
            self.pistol_magazine_item_issued_by = issued_by
            self.save(update_fields=[
                "pistol_magazine_item_issued", "pistol_magazine_item_issued_quantity",
                "pistol_magazine_item_issued_timestamp", "pistol_magazine_item_issued_by",
            ])
        elif item_type == 'rifle_magazine':
            # REC-05: Dedicated rifle magazine tracking field.
            self.rifle_magazine_item_issued = item_name
            self.rifle_magazine_item_issued_quantity = quantity
            self.rifle_magazine_item_issued_timestamp = timestamp
            self.rifle_magazine_item_issued_by = issued_by
            self.save(update_fields=[
                "rifle_magazine_item_issued", "rifle_magazine_item_issued_quantity",
                "rifle_magazine_item_issued_timestamp", "rifle_magazine_item_issued_by",
            ])
        elif item_type == 'ammunition':
            self.ammunition_item_issued = item_name
            self.ammunition_item_issued_quantity = quantity
            self.ammunition_item_issued_timestamp = timestamp
            self.ammunition_item_issued_by = issued_by
            self.save(update_fields=[
                "ammunition_item_issued", "ammunition_item_issued_quantity",
                "ammunition_item_issued_timestamp", "ammunition_item_issued_by",
            ])
        elif item_type == 'pistol_ammunition':
            # REC-06: Dedicated pistol ammunition tracking field.
            self.pistol_ammunition_item_issued = item_name
            self.pistol_ammunition_item_issued_quantity = quantity
            self.pistol_ammunition_item_issued_timestamp = timestamp
            self.pistol_ammunition_item_issued_by = issued_by
            self.save(update_fields=[
                "pistol_ammunition_item_issued", "pistol_ammunition_item_issued_quantity",
                "pistol_ammunition_item_issued_timestamp", "pistol_ammunition_item_issued_by",
            ])
        elif item_type == 'rifle_ammunition':
            # REC-06: Dedicated rifle ammunition tracking field.
            self.rifle_ammunition_item_issued = item_name
            self.rifle_ammunition_item_issued_quantity = quantity
            self.rifle_ammunition_item_issued_timestamp = timestamp
            self.rifle_ammunition_item_issued_by = issued_by
            self.save(update_fields=[
                "rifle_ammunition_item_issued", "rifle_ammunition_item_issued_quantity",
                "rifle_ammunition_item_issued_timestamp", "rifle_ammunition_item_issued_by",
            ])
        elif item_type == 'pistol_holster':
            self.pistol_holster_issued = item_name
            self.pistol_holster_issued_quantity = quantity
            self.pistol_holster_issued_timestamp = timestamp
            self.pistol_holster_issued_by = issued_by
            self.save(update_fields=[
                "pistol_holster_issued", "pistol_holster_issued_quantity",
                "pistol_holster_issued_timestamp", "pistol_holster_issued_by",
            ])
        elif item_type == 'magazine_pouch':
            self.magazine_pouch_issued = item_name
            self.magazine_pouch_issued_quantity = quantity
            self.magazine_pouch_issued_timestamp = timestamp
            self.magazine_pouch_issued_by = issued_by
            self.save(update_fields=[
                "magazine_pouch_issued", "magazine_pouch_issued_quantity",
                "magazine_pouch_issued_timestamp", "magazine_pouch_issued_by",
            ])
        elif item_type == 'rifle_sling':
            self.rifle_sling_issued = item_name
            self.rifle_sling_issued_quantity = quantity
            self.rifle_sling_issued_timestamp = timestamp
            self.rifle_sling_issued_by = issued_by
            self.save(update_fields=[
                "rifle_sling_issued", "rifle_sling_issued_quantity",
                "rifle_sling_issued_timestamp", "rifle_sling_issued_by",
            ])
        elif item_type == 'bandoleer':
            self.bandoleer_issued = item_name
            self.bandoleer_issued_quantity = quantity
            self.bandoleer_issued_timestamp = timestamp
            self.bandoleer_issued_by = issued_by
            self.save(update_fields=[
                "bandoleer_issued", "bandoleer_issued_quantity",
                "bandoleer_issued_timestamp", "bandoleer_issued_by",
            ])
        else:
            raise ValueError("item_type must be one of: 'rifle', 'pistol', 'pistol_magazine', 'rifle_magazine', 'magazine', 'ammunition', 'pistol_ammunition', 'rifle_ammunition', 'pistol_holster', 'magazine_pouch', 'rifle_sling', 'bandoleer'")

    # ── Assignment synchronization ─────────────────────────────────────────────
    def set_assigned(self, item_type, item_name, timestamp, assigned_by, quantity=None):
        """
        Syncs assigned-item tracking fields for the given item type.

        Supported item_type values:
          'rifle'       — updates rifle_item_assigned + timestamp + by
          'pistol'      — updates pistol_item_assigned + timestamp + by
          'magazine'    — updates magazine_item_assigned + quantity + timestamp + by
          'ammunition'  — updates ammunition_item_assigned + quantity + timestamp + by
          'accessory'   — updates accessory_item_assigned + quantity + timestamp + by

        Uses update_fields for a targeted DB write.
        """
        if item_type == 'rifle':
            self.rifle_item_assigned = item_name
            self.rifle_item_assigned_timestamp = timestamp
            self.rifle_item_assigned_by = assigned_by
            self.save(update_fields=["rifle_item_assigned", "rifle_item_assigned_timestamp", "rifle_item_assigned_by"])
        elif item_type == 'pistol':
            self.pistol_item_assigned = item_name
            self.pistol_item_assigned_timestamp = timestamp
            self.pistol_item_assigned_by = assigned_by
            self.save(update_fields=["pistol_item_assigned", "pistol_item_assigned_timestamp", "pistol_item_assigned_by"])
        elif item_type == 'magazine':
            self.magazine_item_assigned = item_name
            self.magazine_item_assigned_quantity = quantity
            self.magazine_item_assigned_timestamp = timestamp
            self.magazine_item_assigned_by = assigned_by
            self.save(update_fields=[
                "magazine_item_assigned", "magazine_item_assigned_quantity",
                "magazine_item_assigned_timestamp", "magazine_item_assigned_by",
            ])
        elif item_type == 'ammunition':
            self.ammunition_item_assigned = item_name
            self.ammunition_item_assigned_quantity = quantity
            self.ammunition_item_assigned_timestamp = timestamp
            self.ammunition_item_assigned_by = assigned_by
            self.save(update_fields=[
                "ammunition_item_assigned", "ammunition_item_assigned_quantity",
                "ammunition_item_assigned_timestamp", "ammunition_item_assigned_by",
            ])
        elif item_type == 'accessory':
            self.accessory_item_assigned = item_name
            self.accessory_item_assigned_quantity = quantity
            self.accessory_item_assigned_timestamp = timestamp
            self.accessory_item_assigned_by = assigned_by
            self.save(update_fields=[
                "accessory_item_assigned", "accessory_item_assigned_quantity",
                "accessory_item_assigned_timestamp", "accessory_item_assigned_by",
            ])
        else:
            raise ValueError("item_type must be one of: 'rifle', 'pistol', 'magazine', 'ammunition', 'accessory'")

    def has_pistol_issued(self):
        """Returns True if this personnel currently has a pistol issued."""
        return bool(self.pistol_item_issued)

    def has_rifle_issued(self):
        """Returns True if this personnel currently has a rifle issued."""
        return bool(self.rifle_item_issued)

    def can_return_pistol(self, pistol_item_id):
        """
        Returns (True, None) if this personnel can return the given pistol,
        else (False, reason).
        """
        if not self.pistol_item_issued:
            return False, f"Personnel {self.Personnel_ID} has no pistol currently issued."
        if self.pistol_item_issued != pistol_item_id:
            return False, (
                f"Personnel {self.Personnel_ID} was issued pistol {self.pistol_item_issued}, "
                f"not {pistol_item_id}."
            )
        return True, None

    def can_return_rifle(self, rifle_item_id):
        """
        Returns (True, None) if this personnel can return the given rifle,
        else (False, reason).
        """
        if not self.rifle_item_issued:
            return False, f"Personnel {self.Personnel_ID} has no rifle currently issued."
        if self.rifle_item_issued != rifle_item_id:
            return False, (
                f"Personnel {self.Personnel_ID} was issued rifle {self.rifle_item_issued}, "
                f"not {rifle_item_id}."
            )
        return True, None

    # FIX DIS. 11: Add can_return equivalents for magazine, ammunition, and accessory.
    # Brings Personnel symmetry with the pistol/rifle can_return_* pattern.
    # magazine_item_issued stores str(magazine) (the magazine's __str__ representation).
    def can_return_magazine(self, magazine_label):
        """
        Returns (True, None) if this personnel can return the given magazine pool.
        Pass magazine_label as str(magazine_instance).
        """
        if not self.magazine_item_issued:
            return False, f"Personnel {self.Personnel_ID} has no magazine currently issued."
        if self.magazine_item_issued != magazine_label:
            return False, (
                f"Personnel {self.Personnel_ID} was issued magazine '{self.magazine_item_issued}', "
                f"not '{magazine_label}'."
            )
        return True, None

    def can_return_ammunition(self, ammunition_label):
        """
        Returns (True, None) if this personnel can return the given ammunition lot.
        Pass ammunition_label as str(ammunition_instance).
        """
        if not self.ammunition_item_issued:
            return False, f"Personnel {self.Personnel_ID} has no ammunition currently issued."
        if self.ammunition_item_issued != ammunition_label:
            return False, (
                f"Personnel {self.Personnel_ID} was issued ammunition '{self.ammunition_item_issued}', "
                f"not '{ammunition_label}'."
            )
        return True, None

    def can_return_accessory(self, accessory_label):
        """
        Returns (True, None) if this personnel can return the given accessory type.
        Pass accessory_label as str(accessory_instance).
        """
        if not self.accessory_item_issued:
            return False, f"Personnel {self.Personnel_ID} has no accessory currently issued."
        if self.accessory_item_issued != accessory_label:
            return False, (
                f"Personnel {self.Personnel_ID} was issued accessory '{self.accessory_item_issued}', "
                f"not '{accessory_label}'."
            )
        return True, None

    # ── Computed Properties ────────────────────────────────────────────────────────
    # These properties derive current issuance state from TransactionLogs,
    # providing a single source of truth independent of denormalized fields.
    # REC-07: Add computed properties to reduce reliance on denormalized fields.
    
    def get_current_pistol(self):
        """
        Returns the currently issued pistol for this personnel by querying TransactionLogs.
        Returns (pistol_object, withdrawal_timestamp) or (None, None) if not issued.
        """
        TransactionLogs = apps.get_model('transactions', 'TransactionLogs')
        log = TransactionLogs.objects.filter(
            personnel_id=self,
            withdraw_pistol__isnull=False,
            return_pistol__isnull=True,
        ).order_by('-withdraw_pistol_timestamp').first()
        if log:
            return log.withdraw_pistol, log.withdraw_pistol_timestamp
        return None, None

    def get_current_rifle(self):
        """
        Returns the currently issued rifle for this personnel by querying TransactionLogs.
        Returns (rifle_object, withdrawal_timestamp) or (None, None) if not issued.
        """
        TransactionLogs = apps.get_model('transactions', 'TransactionLogs')
        log = TransactionLogs.objects.filter(
            personnel_id=self,
            withdraw_rifle__isnull=False,
            return_rifle__isnull=True,
        ).order_by('-withdraw_rifle_timestamp').first()
        if log:
            return log.withdraw_rifle, log.withdraw_rifle_timestamp
        return None, None

    def get_current_pistol_magazine(self):
        """
        Returns the currently issued pistol magazine for this personnel.
        Returns (magazine_object, quantity, withdrawal_timestamp) or (None, None, None).
        """
        TransactionLogs = apps.get_model('transactions', 'TransactionLogs')
        log = TransactionLogs.objects.filter(
            personnel_id=self,
            withdraw_pistol_magazine__isnull=False,
            return_pistol_magazine__isnull=True,
        ).order_by('-withdraw_pistol_magazine_timestamp').first()
        if log:
            return (
                log.withdraw_pistol_magazine,
                log.withdraw_pistol_magazine_quantity,
                log.withdraw_pistol_magazine_timestamp
            )
        return None, None, None

    def get_current_rifle_magazine(self):
        """
        Returns the currently issued rifle magazine for this personnel.
        Returns (magazine_object, quantity, withdrawal_timestamp) or (None, None, None).
        """
        TransactionLogs = apps.get_model('transactions', 'TransactionLogs')
        log = TransactionLogs.objects.filter(
            personnel_id=self,
            withdraw_rifle_magazine__isnull=False,
            return_rifle_magazine__isnull=True,
        ).order_by('-withdraw_rifle_magazine_timestamp').first()
        if log:
            return (
                log.withdraw_rifle_magazine,
                log.withdraw_rifle_magazine_quantity,
                log.withdraw_rifle_magazine_timestamp
            )
        return None, None, None

    def get_current_ammunition(self):
        """
        Returns the currently issued ammunition (combined pistol + rifle) for this personnel.
        Returns dict with 'pistol_ammunition' and 'rifle_ammunition' keys.
        """
        TransactionLogs = apps.get_model('transactions', 'TransactionLogs')
        result = {'pistol': None, 'rifle': None}
        
        # Get pistol ammo
        log = TransactionLogs.objects.filter(
            personnel_id=self,
            withdraw_pistol_ammunition__isnull=False,
            return_pistol_ammunition__isnull=True,
        ).order_by('-withdraw_pistol_ammunition_timestamp').first()
        if log:
            result['pistol'] = {
                'ammunition': log.withdraw_pistol_ammunition,
                'quantity': log.withdraw_pistol_ammunition_quantity,
                'timestamp': log.withdraw_pistol_ammunition_timestamp,
            }
        
        # Get rifle ammo
        log = TransactionLogs.objects.filter(
            personnel_id=self,
            withdraw_rifle_ammunition__isnull=False,
            return_rifle_ammunition__isnull=True,
        ).order_by('-withdraw_rifle_ammunition_timestamp').first()
        if log:
            result['rifle'] = {
                'ammunition': log.withdraw_rifle_ammunition,
                'quantity': log.withdraw_rifle_ammunition_quantity,
                'timestamp': log.withdraw_rifle_ammunition_timestamp,
            }
        return result

    def get_current_accessories(self):
        """
        Returns all currently issued accessories for this personnel.
        Returns dict with accessory type as key and {'quantity', 'timestamp'} as value.
        """
        TransactionLogs = apps.get_model('transactions', 'TransactionLogs')
        result = {}
        
        accessory_fields = [
            ('pistol_holster', 'Pistol Holster'),
            ('magazine_pouch', 'Pistol Magazine Pouch'),
            ('rifle_sling', 'Rifle Sling'),
            ('bandoleer', 'Bandoleer'),
        ]
        
        for field, label in accessory_fields:
            withdraw_field = f'withdraw_{field}'
            return_field = f'return_{field}'
            qty_field = f'{field}_quantity'
            ts_field = f'withdraw_{field}_timestamp'
            
            log = TransactionLogs.objects.filter(
                personnel_id=self,
                **{f'{withdraw_field}__isnull': False},
                **{f'{return_field}__isnull': True},
            ).order_by(f'-{ts_field}').first()
            
            if log:
                result[label] = {
                    'quantity': getattr(log, qty_field),
                    'timestamp': getattr(log, ts_field),
                }
        return result

    def has_any_issued_items(self):
        """
        Returns True if this personnel has any items currently issued.
        More efficient than checking each field individually.
        """
        TransactionLogs = apps.get_model('transactions', 'TransactionLogs')
        return TransactionLogs.objects.filter(
            personnel_id=self,
            log_status__in=['Open', 'Partially Returned'],
        ).exists()

    class Meta:
        verbose_name = "Personnel"
        verbose_name_plural = "Personnel"
        # G8 FIX: DB-level CHECK constraint ensures status is only 'Active' or 'Inactive'.
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=['Active', 'Inactive']),
                name='personnel_status_valid',
            ),
        ]

    def __str__(self):
        return self.get_display_str()

    # Custom validation for AFSN based on rank
    def clean(self):
        """Custom AFSN validation logic"""
        super().clean()
        if self.rank in dict(self.RANKS_ENLISTED):
            if self.AFSN and self.AFSN[0] in '56789':
                if len(self.AFSN) > 6:
                    raise ValidationError("For EP personnel with AFSN starting 5-9, max input is 6 digits.")
            elif self.AFSN and self.AFSN[0] in '1234':
                if len(self.AFSN) > 7:
                    raise ValidationError("For EP personnel with AFSN starting 1-4, max input is 7 digits.")
        elif self.rank in dict(self.RANKS_OFFICER):
            # Officer: allow 'O-' prefix, require numeric part after 'O-'
            if self.AFSN:
                afsn = self.AFSN
                if afsn.startswith('O-'):
                    afsn = afsn[2:]
                if not re.fullmatch(r'\d+', afsn):
                    raise ValidationError("Officer AFSN must be numeric (with optional 'O-' prefix).")
                if len(afsn) < 5 or len(afsn) > 7:
                    raise ValidationError("Officer AFSN must be 5-7 digits (excluding 'O-' prefix).")
        # Validate that issued items actually exist and are truly issued to this personnel
        if self.pistol_item_issued:
            from armguard.apps.inventory.models import Pistol
            try:
                pistol = Pistol.objects.get(pk=self.pistol_item_issued)
                if pistol.item_status != 'Issued' or pistol.item_issued_to != self.Personnel_ID:
                    raise ValidationError({
                        'pistol_item_issued': (
                            f"Pistol {self.pistol_item_issued} is not currently issued to this personnel. "
                            "Clear this field or use a Transaction to issue it properly."
                        )
                    })
            except Pistol.DoesNotExist:
                raise ValidationError({
                    'pistol_item_issued': f"Pistol {self.pistol_item_issued} does not exist."
                })
        if self.rifle_item_issued:
            from armguard.apps.inventory.models import Rifle
            try:
                rifle = Rifle.objects.get(pk=self.rifle_item_issued)
                if rifle.item_status != 'Issued' or rifle.item_issued_to != self.Personnel_ID:
                    raise ValidationError({
                        'rifle_item_issued': (
                            f"Rifle {self.rifle_item_issued} is not currently issued to this personnel. "
                            "Clear this field or use a Transaction to issue it properly."
                        )
                    })
            except Rifle.DoesNotExist:
                raise ValidationError({
                    'rifle_item_issued': f"Rifle {self.rifle_item_issued} does not exist."
                })
        # Cross-validate magazine/ammunition/accessory issued fields against open TransactionLogs.
        # Uses apps.get_model() to avoid circular import (transactions.models imports personnel.models).
        # Only perform this check on existing records (pk set) — new personnel cannot have open logs.
        if self.pk:
            TransactionLogs = apps.get_model('transactions', 'TransactionLogs')
            if self.magazine_item_issued:
                has_open = TransactionLogs.objects.filter(
                    personnel_id=self.pk,
                    withdraw_magazine__isnull=False,
                    return_magazine__isnull=True,
                ).exists()
                if not has_open:
                    raise ValidationError({
                        'magazine_item_issued': (
                            "No open magazine withdrawal record found for this personnel. "
                            "Clear this field or use a Transaction to issue it properly."
                        )
                    })
            if self.ammunition_item_issued:
                has_open = TransactionLogs.objects.filter(
                    personnel_id=self.pk,
                    withdraw_ammunition__isnull=False,
                    return_ammunition__isnull=True,
                ).exists()
                if not has_open:
                    raise ValidationError({
                        'ammunition_item_issued': (
                            "No open ammunition withdrawal record found for this personnel. "
                            "Clear this field or use a Transaction to issue it properly."
                        )
                    })
            if self.pistol_holster_issued or self.magazine_pouch_issued or self.rifle_sling_issued or self.bandoleer_issued:
                has_open_acc = TransactionLogs.objects.filter(
                    personnel_id=self.pk,
                ).filter(
                    models.Q(withdraw_pistol_holster__isnull=False, return_pistol_holster__isnull=True) |
                    models.Q(withdraw_magazine_pouch__isnull=False, return_magazine_pouch__isnull=True) |
                    models.Q(withdraw_rifle_sling__isnull=False, return_rifle_sling__isnull=True) |
                    models.Q(withdraw_bandoleer__isnull=False, return_bandoleer__isnull=True)
                ).exists()
                if not has_open_acc:
                    raise ValidationError({
                        'pistol_holster_issued': (
                            "No open accessory withdrawal record found for this personnel. "
                            "Clear these fields or use a Transaction to issue accessories properly."
                        )
                    })

    # CRUD methods
    @classmethod
    def create_personnel(cls, user, **kwargs):
        """Create and add a Personnel record, checking user authorization."""
        if not (user and (user.is_staff or user.is_superuser)):
            raise PermissionError("User is not authorized to create personnel.")
        return cls.objects.create(**kwargs)

    def update_personnel(self, user, **kwargs):
        """Update only changed fields for this Personnel record, checking user authorization."""
        if not (user and (user.is_staff or user.is_superuser)):
            raise PermissionError("User is not authorized to update personnel.")
        changed = False
        for key, value in kwargs.items():
            old_value = getattr(self, key, None)
            if old_value != value:
                setattr(self, key, value)
                changed = True
        if changed:
            self.save()
        return self

    def delete_personnel(self, user):
        """Delete this Personnel record, checking user authorization."""
        if not (user and (user.is_staff or user.is_superuser)):
            raise PermissionError("User is not authorized to delete personnel.")
        # Delete associated image files
        if self.personnel_image:
            self.personnel_image.delete(save=False)
        if self.qr_code_image:
            self.qr_code_image.delete(save=False)
        self.delete()

    def delete(self, *args, **kwargs):
        """
        FIX DIS. 8: Moved from the top of the class (where it appeared between field
        declarations) to its natural position after the CRUD helper methods.
        Cleans up associated media files before the DB record is removed.
        """
        if self.personnel_image:
            self.personnel_image.delete(save=False)
        if self.qr_code_image:
            self.qr_code_image.delete(save=False)
        # Remove generated ID card PNGs (front, back, combined)
        import os
        pid = self.Personnel_ID
        card_dir = os.path.join(settings.MEDIA_ROOT, 'personnel_id_cards')
        for suffix in (f'{pid}_front.png', f'{pid}_back.png', f'{pid}.png'):
            path = os.path.join(card_dir, suffix)
            try:
                os.remove(path)
            except OSError:
                pass
        super().delete(*args, **kwargs)

    def _delete_old_image(self):
        """Delete old personnel image when updating; rename a NEW upload to a canonical name."""
        old_image_name = None
        if self.pk:
            try:
                old = Personnel.objects.get(pk=self.pk)
                old_image_name = old.personnel_image.name if old.personnel_image else None
                # Delete old personnel image only if it was replaced or cleared
                if old.personnel_image and (old.personnel_image != self.personnel_image or not self.personnel_image):
                    old.personnel_image.delete(save=False)
                # Delete old QR code image if updating or clearing
                if old.qr_code_image and (old.qr_code_image != self.qr_code_image or not self.qr_code_image):
                    old.qr_code_image.delete(save=False)
            except Personnel.DoesNotExist:
                pass
        # Rename ONLY when a genuinely new file is being uploaded (name differs from DB).
        # Re-naming an existing FieldFile would strip the upload_to prefix and break the URL.
        current_name = self.personnel_image.name if self.personnel_image else None
        is_new_upload = (
            self.personnel_image
            and current_name != old_image_name  # changed from what is stored in DB
        )
        if is_new_upload and self.Personnel_ID:
            # upload_to='personnel_images/' already places the file in that folder.
            # Only set the filename here — no subfolder prefix.
            new_name = f"IMG_{self.last_name}_{self.Personnel_ID}.jpeg"
            self.personnel_image.name = new_name



    def save(self, *args, **kwargs):
        # Pop 'user' kwarg so it is not forwarded to Django's Model.save(),
        # which does not accept it.  Pistol/Rifle use this kwarg to set
        # created_by/updated_by; here those fields are set by the caller.
        kwargs.pop('user', None)
        # Normalize fields BEFORE generating filenames or QR codes
        if self.middle_initial:
            self.middle_initial = self.middle_initial.upper()
        if self.rank in dict(self.RANKS_OFFICER):
            if self.first_name:
                self.first_name = self.first_name.upper()
            if self.last_name:
                self.last_name = self.last_name.upper()
        else:
            if self.first_name:
                self.first_name = ' '.join([part.capitalize() for part in self.first_name.split()])
            if self.last_name:
                self.last_name = ' '.join([part.capitalize() for part in self.last_name.split()])

        # Set created timestamp if not set
        if not self.created:
            self.created = timezone.now()
        # Always update updated timestamp
        self.updated = timezone.now()

        regenerate_qr = False

        # Only set Personnel_ID and regenerate QR on creation
        if not self.pk:
            # FIX DIS. 9: Removed duplicate name normalization block — names were already
            # normalized in the block above (which runs on every save). Only the
            # ID generation code and O- AFSN prefix (new-record-only logic) remain here.
            dt = self.created if self.created else timezone.now()
            if self.rank in dict(self.RANKS_ENLISTED):
                code = f"PEP-{self.AFSN}-{dt.strftime('%H%d%M%m%y')}"
            elif self.rank in dict(self.RANKS_OFFICER):
                if not self.AFSN.startswith("O-"):
                    self.AFSN = f"O-{self.AFSN}"
                code = f"POF_{self.AFSN}-{dt.strftime('%H%d%M%m%y')}"
            else:
                code = f"P{self.AFSN}-{dt.strftime('%H%d%M%m%y')}"
            object.__setattr__(self, 'Personnel_ID', code)
            self.qr_code = code
            regenerate_qr = True
        else:
            # On update, only regenerate QR if Personnel_ID changes
            try:
                old = Personnel.objects.get(pk=self.pk)
                if getattr(self, 'Personnel_ID', None) != getattr(old, 'Personnel_ID', None):
                    regenerate_qr = True
            except Personnel.DoesNotExist:
                regenerate_qr = True

        # Delete/rename images NOW — Personnel_ID is guaranteed to be set at this point
        self._delete_old_image()

        # Generate QR code string based on Personnel_ID and created date (hhddminmmYY)
        if self.created:
            dt = self.created
        else:
            dt = timezone.now()
        self.qr_code = self.Personnel_ID

        # Only regenerate QR code image if essential fields changed or file is missing
        import os
        qr_image_missing = False
        if self.qr_code_image and self.qr_code_image.name:
            qr_image_path = os.path.join(settings.MEDIA_ROOT, self.qr_code_image.name)
            if not os.path.isfile(qr_image_path):
                qr_image_missing = True
        if regenerate_qr or qr_image_missing:
            # Delete old QR code image file if it exists
            if self.pk:
                try:
                    old = Personnel.objects.get(pk=self.pk)
                    if old.qr_code_image and old.qr_code_image.name:
                        old.qr_code_image.delete(save=False)
                except Personnel.DoesNotExist:
                    pass
            buffer = generate_qr_code_to_buffer(self.qr_code)
            filename = f"{self.Personnel_ID}.png"
            self.qr_code_image.save(filename, ContentFile(buffer.read()), save=False)

        super().save(*args, **kwargs)
