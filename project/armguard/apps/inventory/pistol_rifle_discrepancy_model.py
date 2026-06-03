from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


DISCREPANCY_TYPE_CHOICES = [
    ('Missing',                'Missing'),
    ('Damaged',                'Damaged'),
    ('Wrong Serial',           'Wrong Serial'),
    ('Condition Mismatch',     'Condition Mismatch'),
    ('Incomplete Accessories', 'Incomplete Accessories'),
    ('Others',                 'Others'),
]

DISCREPANCY_STATUS_CHOICES = [
    ('Open',          'Open'),
    ('Under Review',  'Under Review'),
    ('Resolved',      'Resolved'),
    ('Closed',        'Closed'),
]


class FirearmDiscrepancy(models.Model):
    """
    Records a discrepancy discovered during a firearms inspection or transaction.

    Fields
    ------
    pistol / rifle      : exactly one must be set (the other stays NULL).
                          firearm_type is derived from whichever FK is set.
    issuer              : the armorer / personnel who issued the firearm.
    withdrawer          : the personnel who withdrew / received the firearm.
    related_transaction : optional link to the originating Transaction record.
    discrepancy_type    : category of the discrepancy.
    description         : free-text details.
    status              : lifecycle state (Open → Resolved etc.).
    reported_by         : FK to User who logged the record.
    reported_at         : timestamp when the record was created.
    resolved_by         : FK to User who resolved it (optional).
    resolved_at         : timestamp of resolution (optional).
    resolution_notes    : free-text explanation of how it was resolved (optional).
    """

    # Only one of these two FK fields should be set per record.
    pistol = models.ForeignKey(
        'inventory.Pistol',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='discrepancies',
    )
    rifle = models.ForeignKey(
        'inventory.Rifle',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='discrepancies',
    )

    # The armorer / staff member who issued the firearm.
    issuer = models.ForeignKey(
        'personnel.Personnel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='discrepancies_issued',
    )

    # The personnel member who withdrew / received the firearm.
    withdrawer = models.ForeignKey(
        'personnel.Personnel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='discrepancies_withdrawn',
    )

    # Optional link to the source transaction.
    related_transaction = models.ForeignKey(
        'transactions.Transaction',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='discrepancies',
    )

    discrepancy_type = models.CharField(
        max_length=50,
        choices=DISCREPANCY_TYPE_CHOICES,
    )
    description = models.TextField(
        help_text='Detailed description of the discrepancy.',
    )
    status = models.CharField(
        max_length=20,
        choices=DISCREPANCY_STATUS_CHOICES,
        default='Open',
    )

    # ── Audit fields ─────────────────────────────────────────────────────────
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='discrepancies_reported',
        help_text='User who reported this discrepancy.',
    )
    reported_at = models.DateTimeField(default=timezone.now)

    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='discrepancies_resolved',
        help_text='User who resolved this discrepancy.',
    )
    resolved_at = models.DateTimeField(blank=True, null=True)
    resolution_notes = models.TextField(blank=True, null=True)

    # Photo evidence — up to 5 images (image is slot 1, image_2–5 are additional slots).
    image = models.ImageField(
        upload_to='discrepancy_images/',
        blank=True,
        null=True,
        help_text='Optional photo evidence of the discrepancy.',
    )
    image_2 = models.ImageField(upload_to='discrepancy_images/', blank=True, null=True)
    image_3 = models.ImageField(upload_to='discrepancy_images/', blank=True, null=True)
    image_4 = models.ImageField(upload_to='discrepancy_images/', blank=True, null=True)
    image_5 = models.ImageField(upload_to='discrepancy_images/', blank=True, null=True)

    # ── Accessory / consumable fields ────────────────────────────────────────
    # When the discrepancy concerns a consumable rather than the firearm itself
    # (e.g., a missing rifle sling or magazine), set accessory_type to identify
    # the item. pistol / rifle FKs may still be set to link to the issuing firearm.
    ACCESSORY_TYPE_CHOICES = [
        ('Pistol Magazine',    'Pistol Magazine'),
        ('Pistol Ammunition',  'Pistol Ammunition'),
        ('Pistol Holster',     'Pistol Holster'),
        ('Magazine Pouch',     'Magazine Pouch'),
        ('Rifle Magazine',     'Rifle Magazine'),
        ('Rifle Ammunition',   'Rifle Ammunition'),
        ('Rifle Sling',        'Rifle Sling'),
        ('Bandoleer',          'Bandoleer'),
    ]
    accessory_type = models.CharField(
        max_length=50,
        choices=ACCESSORY_TYPE_CHOICES,
        null=True,
        blank=True,
        help_text='Set when the discrepancy relates to a consumable/accessory rather than the firearm itself.',
    )
    accessory_quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Quantity of the consumable that is discrepant.',
    )

    class Meta:
        app_label = 'inventory'
        ordering = ['-reported_at']
        verbose_name = 'Firearm Discrepancy'
        verbose_name_plural = 'Firearm Discrepancies'

    # ── Derived property ──────────────────────────────────────────────────────
    @property
    def firearm_type(self):
        """Return 'Pistol', 'Rifle', the accessory_type label, or None."""
        if self.pistol_id is not None:
            return 'Pistol'
        if self.rifle_id is not None:
            return 'Rifle'
        if self.accessory_type:
            return self.accessory_type
        return None

    # ── Validation ────────────────────────────────────────────────────────────
    def clean(self):
        has_pistol = self.pistol_id is not None
        has_rifle = self.rifle_id is not None
        has_accessory = bool(self.accessory_type)
        if has_pistol and has_rifle:
            raise ValidationError(
                'A discrepancy must link to either a Pistol or a Rifle — not both.'
            )
        if not has_pistol and not has_rifle and not has_accessory:
            raise ValidationError(
                'A discrepancy must link to a Pistol, a Rifle, or specify an accessory type.'
            )

    def save(self, *args, **kwargs):
        self.clean()  # L-4: was full_clean() which calls validators on all fields incl. file fields unnecessarily
        super().save(*args, **kwargs)

    def __str__(self):
        item = (
            self.pistol_id if self.pistol_id is not None
            else self.rifle_id if self.rifle_id is not None
            else '—'
        )
        return (
            f'Discrepancy #{self.pk} – '
            f'{self.firearm_type or "Unknown"} {item} '
            f'[{self.discrepancy_type}] ({self.status})'
        )
