from django.db import models
from django.utils import timezone


DISCREPANCY_TYPE_CHOICES = [
    ('Missing',                'Missing'),
    ('Damaged',                'Damaged'),
    ('Wrong Serial',           'Wrong Serial'),
    ('Condition Mismatch',     'Condition Mismatch'),
    ('Extra Rounds',           'Extra Rounds'),
    ('Incomplete Accessories', 'Incomplete Accessories'),
    ('Others',                 'Others'),
]

DISCREPANCY_STATUS_CHOICES = [
    ('Open',          'Open'),
    ('Under Review',  'Under Review'),
    ('Resolved',      'Resolved'),
    ('Closed',        'Closed'),
]

FIREARM_TYPE_CHOICES = [
    ('Pistol', 'Pistol'),
    ('Rifle',  'Rifle'),
]


class FirearmDiscrepancy(models.Model):
    """
    Records a discrepancy discovered during a firearms inspection or transaction.

    Fields
    ------
    firearm_type    : whether the discrepancy involves a Pistol or a Rifle.
    pistol / rifle  : exactly one should be set (the other stays NULL).
    issuer          : the armorer / personnel who issued the firearm.
    withdrawer      : the personnel who withdrew / received the firearm.
    related_transaction : optional link to the originating Transaction record.
    discrepancy_type    : category of the discrepancy.
    description         : free-text details.
    status              : lifecycle state (Open → Resolved etc.).
    reported_by         : username of the staff member who logged the record.
    reported_at         : timestamp when the record was created.
    resolved_by         : username of the staff member who resolved it (optional).
    resolved_at         : timestamp of resolution (optional).
    resolution_notes    : free-text explanation of how it was resolved (optional).
    """

    firearm_type = models.CharField(
        max_length=10,
        choices=FIREARM_TYPE_CHOICES,
    )

    # Only one of these two FK fields should be set per record.
    # String references avoid circular imports (transactions → inventory already exists).
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
    reported_by = models.CharField(
        max_length=100,
        help_text='Username of the staff member who reported this discrepancy.',
    )
    reported_at = models.DateTimeField(default=timezone.now)

    resolved_by = models.CharField(max_length=100, blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    resolution_notes = models.TextField(blank=True, null=True)

    class Meta:
        app_label = 'inventory'
        ordering = ['-reported_at']
        verbose_name = 'Firearm Discrepancy'
        verbose_name_plural = 'Firearm Discrepancies'

    def __str__(self):
        item = self.pistol_id or self.rifle_id or '—'
        return f'Discrepancy #{self.pk} – {self.firearm_type} {item} [{self.discrepancy_type}] ({self.status})'
