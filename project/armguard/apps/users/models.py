"""
ArmGuard RDS V1 — Users app models.

Models:
  UserProfile     — extends built-in User with armory role + single-session key
  AuditLog        — persistent audit trail with user-agent and integrity hash
  DeletedRecord   — soft-delete preservation: snapshot of deleted objects
"""
import hashlib
import json
import logging
from django.db import models
from django.conf import settings
from django.db.models.signals import post_save, m2m_changed
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

logger = logging.getLogger(__name__)


ROLE_CHOICES = [
    ('System Administrator', 'System Administrator'),
    ('Administrator — View Only', 'Administrator — View Only'),
    ('Administrator — Edit & Add', 'Administrator — Edit & Add'),
    ('Armorer', 'Armorer'),
]


def _get_user_agent(request):
    """Extract the HTTP User-Agent header (truncated to 512 chars)."""
    if request is None:
        return ''
    return request.META.get('HTTP_USER_AGENT', '')[:512]


def _get_client_ip(request):
    """Extract the real client IP, handling reverse-proxy X-Forwarded-For headers.

    Uses the LAST entry in X-Forwarded-For, which is written by the immediate
    upstream proxy (Nginx) and cannot be forged by the client.  The first entry
    is client-controlled and trivially spoofed.
    """
    if request is None:
        return None
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[-1].strip()
    return request.META.get('REMOTE_ADDR')


class UserProfile(models.Model):
    """
    Extends the built-in User with an armory role.
    Created automatically when a new User is saved.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
        primary_key=True,
    )
    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        default='Armorer',
        help_text="System role for this user. System Administrator = full admin access; Administrator = full access; Armorer = transactions and logs.",
    )
    # G4 FIX: Tracks the session key of the most-recently authenticated session.
    # SingleSessionMiddleware uses this to invalidate any older concurrent sessions.
    last_session_key = models.CharField(
        max_length=40,
        blank=True,
        null=True,
        help_text="Session key from the last successful login. Used for single-session enforcement.",
    )
    # ── Per-module granular permissions (Administrator role only) ─────────────
    # Superusers and System Administrators always have full access regardless
    # of these flags. Armorers have fixed access regardless of these flags.
    # All flags default to False; Group assignment sets appropriate defaults.

    # Inventory module
    perm_inventory_view   = models.BooleanField(default=False, help_text="May view inventory lists (pistols, rifles, ammo, magazines, accessories).")
    perm_inventory_add    = models.BooleanField(default=False, help_text="May create new inventory records.")
    perm_inventory_edit   = models.BooleanField(default=False, help_text="May edit existing inventory records.")
    perm_inventory_delete = models.BooleanField(default=False, help_text="May delete inventory records.")

    # Personnel module
    perm_personnel_view   = models.BooleanField(default=False, help_text="May view personnel list and detail pages.")
    perm_personnel_add    = models.BooleanField(default=False, help_text="May create new personnel records.")
    perm_personnel_edit   = models.BooleanField(default=False, help_text="May edit personnel records and assign weapons.")
    perm_personnel_delete = models.BooleanField(default=False, help_text="May delete personnel records.")

    # Transactions module
    perm_transaction_view   = models.BooleanField(default=False, help_text="May view transaction list and detail pages.")
    perm_transaction_create = models.BooleanField(default=False, help_text="May create new withdrawal/return transactions.")

    # Reports & Print module (separate flags)
    perm_reports = models.BooleanField(default=False, help_text="May view and download analytical reports.")
    perm_print   = models.BooleanField(default=False, help_text="May access the Print module: generate/print ID cards, item tags, and PDF transaction forms.")

    # User management module
    perm_users_manage = models.BooleanField(default=False, help_text="May view, create, edit, and delete user accounts.")

    # ── Per-user two-factor authentication control ─────────────────────────────
    require_2fa = models.BooleanField(
        default=True,
        help_text=(
            'Require TOTP two-factor authentication for this specific user. '
            'Only takes effect when the site-wide 2FA setting is also ON. '
            'Uncheck to exempt this account from 2FA enforcement.'
        ),
    )

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class AuditLog(models.Model):
    """
    G3/G4 FIX: Persistent database audit trail.

    Captures authentication events (LOGIN/LOGOUT) here; CRUD events on
    Transaction/Personnel/Inventory models are captured by the signals in
    armguard/apps/transactions/signals.py, which also write a record here.

    Fields added in Session 10:
      user_agent     — browser/client user-agent string for endpoint tracking
      integrity_hash — SHA-256 of (timestamp+user+action+message) to detect tampering
    """
    ACTION_CHOICES = [
        ('CREATE',       'Create'),
        ('UPDATE',       'Update'),
        ('DELETE',       'Delete'),
        ('LOGIN',        'Login'),
        ('LOGOUT',       'Logout'),
        ('LOGIN_FAILED', 'Login Failed'),
        ('OTP_FAILED',   'OTP Failed'),
        ('OTHER',        'Other'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100, blank=True)
    object_pk = models.CharField(max_length=100, blank=True)
    message = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(
        max_length=512,
        blank=True,
        help_text="HTTP User-Agent header from the request.",
    )
    integrity_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA-256 of (timestamp + username + action + message) — set on save.",
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ['-timestamp']

    def __str__(self):
        who = self.user.username if self.user_id else '(anonymous)'
        return f"[{self.timestamp:%Y-%m-%d %H:%M:%S}] {who} — {self.action} {self.model_name}"

    def compute_hash(self):
        """Return SHA-256 hex digest of core immutable fields."""
        username = self.user.username if self.user_id else ''
        ts = self.timestamp.isoformat() if self.timestamp else ''
        raw = f"{ts}|{username}|{self.action}|{self.message}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def verify_integrity(self):
        """Return True if stored integrity_hash matches re-computed hash."""
        if not self.integrity_hash:
            return False
        return self.integrity_hash == self.compute_hash()

    def save(self, *args, **kwargs):
        """Compute integrity_hash after the first INSERT so timestamp is available."""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.integrity_hash:
            # Use update() to avoid a recursive save() call.
            computed = self.compute_hash()
            AuditLog.objects.filter(pk=self.pk).update(integrity_hash=computed)
            self.integrity_hash = computed


class ActivityLog(models.Model):
    """
    Request-level activity log. Every HTTP request handled by Django is recorded
    here via ActivityLogMiddleware (armguard.middleware.activity).

    Captures: who, what page, what action, when, from where, how long it took,
    what they searched for, and the HTTP result code.
    """
    METHOD_CHOICES = [
        ('GET',    'GET'),
        ('POST',   'POST'),
        ('PUT',    'PUT'),
        ('PATCH',  'PATCH'),
        ('DELETE', 'DELETE'),
        ('HEAD',   'HEAD'),
        ('OTHER',  'OTHER'),
    ]

    # ── Who ──────────────────────────────────────────────────────────────────
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs',
        help_text="Authenticated user; null for anonymous requests.",
    )
    session_key = models.CharField(
        max_length=40, blank=True,
        help_text='Django session key (links anonymous requests across a session).',
    )

    # ── What ─────────────────────────────────────────────────────────────────
    method = models.CharField(max_length=6, choices=METHOD_CHOICES, default='GET')
    path = models.CharField(
        max_length=2048,
        help_text='Request path (URL without scheme/host).',
    )
    query_string = models.TextField(
        blank=True,
        help_text="Raw query string (e.g. 'q=pistol&status=Active').",
    )
    view_name = models.CharField(
        max_length=255, blank=True,
        help_text="Resolved Django URL name (e.g. 'transactions:create').",  # noqa: E501
    )
    referer = models.CharField(
        max_length=2048, blank=True,
        help_text='HTTP Referer header — the page the user came from.',
    )

    # ── Result ───────────────────────────────────────────────────────────────
    status_code = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="HTTP response status code.",
    )
    response_ms = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Response time in milliseconds.",
    )

    # ── Where ────────────────────────────────────────────────────────────────
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)

    # ── Classification (auto-set by middleware) ───────────────────────────────
    FLAG_NORMAL     = 'NORMAL'
    FLAG_SLOW       = 'SLOW'
    FLAG_WARNING    = 'WARNING'
    FLAG_SUSPICIOUS = 'SUSPICIOUS'
    FLAG_ERROR      = 'ERROR'
    FLAG_CHOICES = [
        ('NORMAL',     'Normal'),
        ('SLOW',       'Slow  (> 2 s)'),
        ('WARNING',    'Warning  (404)'),
        ('SUSPICIOUS', 'Suspicious  (401 / 403)'),
        ('ERROR',      'Error  (5xx / exception)'),
    ]
    flag = models.CharField(
        max_length=12, choices=FLAG_CHOICES, default='NORMAL', db_index=True,
        help_text="Auto-classified severity of this request.",
    )

    # ── Error detail (only populated on uncaught exceptions) ─────────────────
    exception_type = models.CharField(
        max_length=200, blank=True,
        help_text="Python exception class name captured before Django's 500 handler ran.",
    )
    exception_message = models.TextField(
        blank=True,
        help_text="Exception message text.",
    )

    # ── Search tracking ───────────────────────────────────────────────────────
    search_query = models.CharField(
        max_length=500, blank=True, db_index=True,
        help_text='Value of ?q=, ?search=, or ?query= param — empty if not a search request.',
    )

    # ── When ─────────────────────────────────────────────────────────────────
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp'],        name='users_activ_user_id_8a5363_idx'),
            models.Index(fields=['path', '-timestamp'],        name='users_activ_path_873007_idx'),
            models.Index(fields=['status_code', '-timestamp'], name='users_activ_status__cc100a_idx'),
            models.Index(fields=['flag', '-timestamp'],        name='users_activ_flag_04e3b5_idx'),
        ]

    def __str__(self):
        who = self.user.username if self.user_id else '(anon)'
        return f"[{self.timestamp:%Y-%m-%d %H:%M:%S}] {who} {self.method} {self.path} → {self.status_code}"


class DeletedRecord(models.Model):
    """
    Soft-delete preservation — captures a JSON snapshot of an object's data
    before it is permanently removed from the database.

    Usage (in delete signals or views):
        DeletedRecord.objects.create(
            model_name='Transaction',
            object_pk=str(obj.pk),
            data=serializers.serialize('json', [obj]),
            deleted_by=request.user,
        )
    """
    model_name = models.CharField(max_length=100)
    object_pk = models.CharField(max_length=100)
    data = models.TextField(help_text="JSON snapshot of the deleted object.")
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deletions',
    )
    deleted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Deleted Record"
        verbose_name_plural = "Deleted Records"
        ordering = ['-deleted_at']

    def __str__(self):
        who = self.deleted_by.username if self.deleted_by_id else '(system)'
        return f"[{self.deleted_at:%Y-%m-%d %H:%M:%S}] {who} deleted {self.model_name} #{self.object_pk}"


class PasswordHistory(models.Model):
    """
    G16-EXT: Stores the N most recent hashed passwords for a user.

    Records are added by UserCreateView and UserUpdateView when a password
    is set or changed.  The PasswordHistoryValidator checks against these
    records to prevent password reuse.

    The raw password is NEVER stored — only the hashed form that Django
    places in User.password (e.g. 'pbkdf2_sha256$...').
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='password_history',
    )
    password_hash = models.CharField(
        max_length=255,
        help_text="Hashed password (User.password value) stored for history comparison.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Password History"
        verbose_name_plural = "Password Histories"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} password set at {self.created_at:%Y-%m-%d %H:%M:%S}"


# ── System Settings (singleton) ───────────────────────────────────────────────

class SystemSettings(models.Model):
    """
    Singleton model for site-wide configurable settings editable by superusers
    through the web UI — no .env file edit or server restart required.

    Always access via SystemSettings.get() which auto-seeds from settings.py defaults.
    """
    # Report signature block — Commander
    commander_name        = models.CharField(max_length=100, blank=True, default='')
    commander_rank        = models.CharField(max_length=50,  blank=True, default='')
    commander_branch      = models.CharField(max_length=20,  blank=True, default='PAF')
    commander_designation = models.CharField(max_length=100, blank=True, default='Squadron Commander')
    # Armorer branch label shown on reports
    armorer_branch        = models.CharField(max_length=20,  blank=True, default='PAF')
    # Inventory limits
    pistol_magazine_max_qty = models.PositiveSmallIntegerField(default=4)
    rifle_magazine_max_qty  = models.PositiveSmallIntegerField(default=2, null=True, blank=True,
                                  help_text='Maximum rifle magazines per withdrawal (default: 2). Leave blank to use system default.')
    # Unit display name (used in report headers etc.)
    unit_name = models.CharField(max_length=150, blank=True, default='950th CEWW')

    # ── Branding ──────────────────────────────────────────────────────────────
    app_logo = models.ImageField(
        upload_to='site/',
        blank=True,
        null=True,
        help_text='Custom logo displayed in the sidebar. Recommended: square PNG, at least 80×80 px.',
    )


    # ── Security & Authentication policy ─────────────────────────────────────
    mfa_required = models.BooleanField(
        default=True,
        help_text='Require two-factor authentication (2FA/TOTP) for all users.'
    )
    password_min_length = models.PositiveSmallIntegerField(
        default=8,
        help_text='Minimum number of characters required for user passwords (1–128).'
    )
    password_history_count = models.PositiveSmallIntegerField(
        default=5,
        help_text='Number of previous passwords a user may not reuse (0 = no restriction).'
    )

    # ── Per-role idle session timeout ─────────────────────────────────────────
    # After this many seconds of inactivity the browser shows a 60-second
    # warning then auto-logs the user out.  0 = disabled for that role.
    timeout_system_admin = models.PositiveIntegerField(
        default=1800,
        help_text='Idle timeout in seconds for System Administrator accounts (0 = never).',
    )
    timeout_admin_view_only = models.PositiveIntegerField(
        default=1800,
        help_text='Idle timeout in seconds for Administrator — View Only accounts (0 = never).',
    )
    timeout_admin_edit_add = models.PositiveIntegerField(
        default=1800,
        help_text='Idle timeout in seconds for Administrator — Edit & Add accounts (0 = never).',
    )
    timeout_armorer = models.PositiveIntegerField(
        default=3600,
        help_text='Idle timeout in seconds for Armorer accounts (0 = never).',
    )
    timeout_superuser = models.PositiveIntegerField(
        default=0,
        help_text='Idle timeout in seconds for Superuser accounts (0 = never). Default: disabled.',
    )

    # ── Per-purpose weapon field visibility ───────────────────────────────────
    # Controls which weapon columns (pistol / rifle) are shown on the
    # New Transaction form for each purpose.  Editable via System Settings.
    purpose_duty_sentinel_show_pistol  = models.BooleanField(default=True)
    purpose_duty_sentinel_show_rifle   = models.BooleanField(default=False)
    purpose_duty_vigil_show_pistol     = models.BooleanField(default=False)
    purpose_duty_vigil_show_rifle      = models.BooleanField(default=True)
    purpose_duty_security_show_pistol  = models.BooleanField(default=True)
    purpose_duty_security_show_rifle   = models.BooleanField(default=True)
    purpose_honor_guard_show_pistol    = models.BooleanField(default=False)
    purpose_honor_guard_show_rifle     = models.BooleanField(default=True)
    purpose_others_show_pistol         = models.BooleanField(default=True)
    purpose_others_show_rifle          = models.BooleanField(default=True)
    purpose_orex_show_pistol           = models.BooleanField(default=True)
    purpose_orex_show_rifle            = models.BooleanField(default=True)

    # ── TR / PAR transaction defaults ────────────────────────────────────────
    tr_default_return_hours = models.PositiveSmallIntegerField(
        default=24,
        help_text='Default TR return deadline pre-filled on the New Transaction form (hours from time of issuance).',
    )
    require_par_document = models.BooleanField(
        default=True,
        help_text='Require upload of a signed PAR document (PDF) when Issuance Type is PAR.',
    )
    default_issuance_type = models.CharField(
        max_length=50,
        default='TR (Temporary Receipt)',
        choices=[
            ('TR (Temporary Receipt)', 'TR (Temporary Receipt)'),
            ('PAR (Property Acknowledgement Receipt)', 'PAR (Property Acknowledgement Receipt)'),
        ],
        help_text='Pre-selected Issuance Type when the New Transaction form first loads.',
    )

    # ── Per-purpose auto-consumable assignment ────────────────────────────────
    # When True the form auto-assigns magazines and ammunition for that purpose.
    purpose_duty_sentinel_auto_consumables = models.BooleanField(default=True,  help_text='Auto-assign magazines & ammunition for Duty Sentinel withdrawals.')
    purpose_duty_vigil_auto_consumables    = models.BooleanField(default=False, help_text='Auto-assign magazines & ammunition for Duty Vigil withdrawals.')
    purpose_duty_security_auto_consumables = models.BooleanField(default=True,  help_text='Auto-assign magazines & ammunition for Duty Security withdrawals.')
    purpose_honor_guard_auto_consumables   = models.BooleanField(default=False, help_text='Auto-assign magazines & ammunition for Honor Guard withdrawals.')
    purpose_others_auto_consumables        = models.BooleanField(default=False, help_text='Auto-assign magazines & ammunition for Others withdrawals.')
    purpose_orex_auto_consumables          = models.BooleanField(default=True,  help_text='Auto-assign magazines & ammunition for OREX withdrawals.')

    # ── Per-purpose auto-accessory assignment ────────────────────────────────
    # When True the form auto-assigns standard accessories for the weapon type
    # being issued (pistol → holster + mag pouch; rifle → sling).
    purpose_duty_sentinel_auto_accessories = models.BooleanField(default=True,  help_text='Auto-assign accessories for Duty Sentinel withdrawals.')
    purpose_duty_vigil_auto_accessories    = models.BooleanField(default=False, help_text='Auto-assign accessories for Duty Vigil withdrawals.')
    purpose_duty_security_auto_accessories = models.BooleanField(default=False, help_text='Auto-assign accessories for Duty Security withdrawals.')
    purpose_honor_guard_auto_accessories   = models.BooleanField(default=False, help_text='Auto-assign accessories for Honor Guard withdrawals.')
    purpose_others_auto_accessories        = models.BooleanField(default=False, help_text='Auto-assign accessories for Others withdrawals.')
    purpose_orex_auto_accessories          = models.BooleanField(default=False, help_text='Auto-assign accessories for OREX withdrawals.')

    # ── Standard loadout defaults — Duty Sentinel ─────────────────────────────
    duty_sentinel_holster_qty       = models.PositiveSmallIntegerField(default=1,   help_text='Pistol holsters auto-issued per Duty Sentinel withdrawal.')
    duty_sentinel_mag_pouch_qty     = models.PositiveSmallIntegerField(default=3,   help_text='Magazine pouches auto-issued per Duty Sentinel withdrawal.')
    duty_sentinel_pistol_mag_qty    = models.PositiveSmallIntegerField(default=4,   help_text='Pistol magazines auto-issued per Duty Sentinel withdrawal.')
    duty_sentinel_pistol_ammo_qty   = models.PositiveSmallIntegerField(default=42,  help_text='Pistol ammunition rounds auto-issued per Duty Sentinel withdrawal.')
    duty_sentinel_rifle_sling_qty   = models.PositiveSmallIntegerField(default=1,   help_text='Rifle slings auto-issued per Duty Sentinel withdrawal.')
    duty_sentinel_rifle_short_mag_qty = models.PositiveSmallIntegerField(default=7, help_text='Rifle Short (20-rd) magazines auto-issued per Duty Sentinel withdrawal.')
    duty_sentinel_rifle_long_mag_qty  = models.PositiveSmallIntegerField(default=7, help_text='Rifle Long (30-rd) magazines auto-issued per Duty Sentinel withdrawal.')
    duty_sentinel_rifle_ammo_qty    = models.PositiveSmallIntegerField(default=210, help_text='Rifle ammunition rounds auto-issued per Duty Sentinel withdrawal.')
    duty_sentinel_bandoleer_qty     = models.PositiveSmallIntegerField(default=0,   help_text='Bandoleers auto-issued per Duty Sentinel withdrawal.')

    # ── Standard loadout defaults — Duty Vigil ────────────────────────────────
    duty_vigil_holster_qty       = models.PositiveSmallIntegerField(default=1,   help_text='Pistol holsters auto-issued per Duty Vigil withdrawal.')
    duty_vigil_mag_pouch_qty     = models.PositiveSmallIntegerField(default=1,   help_text='Magazine pouches auto-issued per Duty Vigil withdrawal.')
    duty_vigil_pistol_mag_qty    = models.PositiveSmallIntegerField(default=2,   help_text='Pistol magazines auto-issued per Duty Vigil withdrawal.')
    duty_vigil_pistol_ammo_qty   = models.PositiveSmallIntegerField(default=21,  help_text='Pistol ammunition rounds auto-issued per Duty Vigil withdrawal.')
    duty_vigil_rifle_sling_qty   = models.PositiveSmallIntegerField(default=1,   help_text='Rifle slings auto-issued per Duty Vigil withdrawal.')
    duty_vigil_rifle_short_mag_qty = models.PositiveSmallIntegerField(default=7, help_text='Rifle Short (20-rd) magazines auto-issued per Duty Vigil withdrawal.')
    duty_vigil_rifle_long_mag_qty  = models.PositiveSmallIntegerField(default=7, help_text='Rifle Long (30-rd) magazines auto-issued per Duty Vigil withdrawal.')
    duty_vigil_rifle_ammo_qty    = models.PositiveSmallIntegerField(default=210, help_text='Rifle ammunition rounds auto-issued per Duty Vigil withdrawal.')
    duty_vigil_bandoleer_qty     = models.PositiveSmallIntegerField(default=0,   help_text='Bandoleers auto-issued per Duty Vigil withdrawal.')

    # ── Standard loadout defaults — Duty Security ─────────────────────────────
    duty_security_holster_qty       = models.PositiveSmallIntegerField(default=1,   help_text='Pistol holsters auto-issued per Duty Security withdrawal.')
    duty_security_mag_pouch_qty     = models.PositiveSmallIntegerField(default=1,   help_text='Magazine pouches auto-issued per Duty Security withdrawal.')
    duty_security_pistol_mag_qty    = models.PositiveSmallIntegerField(default=2,   help_text='Pistol magazines auto-issued per Duty Security withdrawal.')
    duty_security_pistol_ammo_qty   = models.PositiveSmallIntegerField(default=21,  help_text='Pistol ammunition rounds auto-issued per Duty Security withdrawal.')
    duty_security_rifle_sling_qty   = models.PositiveSmallIntegerField(default=1,   help_text='Rifle slings auto-issued per Duty Security withdrawal.')
    duty_security_rifle_short_mag_qty = models.PositiveSmallIntegerField(default=7, help_text='Rifle Short (20-rd) magazines auto-issued per Duty Security withdrawal.')
    duty_security_rifle_long_mag_qty  = models.PositiveSmallIntegerField(default=7, help_text='Rifle Long (30-rd) magazines auto-issued per Duty Security withdrawal.')
    duty_security_rifle_ammo_qty    = models.PositiveSmallIntegerField(default=210, help_text='Rifle ammunition rounds auto-issued per Duty Security withdrawal.')
    duty_security_bandoleer_qty     = models.PositiveSmallIntegerField(default=0,   help_text='Bandoleers auto-issued per Duty Security withdrawal.')

    # ── Standard loadout defaults — Honor Guard ───────────────────────────────
    honor_guard_holster_qty       = models.PositiveSmallIntegerField(default=1,   help_text='Pistol holsters auto-issued per Honor Guard withdrawal.')
    honor_guard_mag_pouch_qty     = models.PositiveSmallIntegerField(default=1,   help_text='Magazine pouches auto-issued per Honor Guard withdrawal.')
    honor_guard_pistol_mag_qty    = models.PositiveSmallIntegerField(default=2,   help_text='Pistol magazines auto-issued per Honor Guard withdrawal.')
    honor_guard_pistol_ammo_qty   = models.PositiveSmallIntegerField(default=21,  help_text='Pistol ammunition rounds auto-issued per Honor Guard withdrawal.')
    honor_guard_rifle_sling_qty   = models.PositiveSmallIntegerField(default=1,   help_text='Rifle slings auto-issued per Honor Guard withdrawal.')
    honor_guard_rifle_short_mag_qty = models.PositiveSmallIntegerField(default=7, help_text='Rifle Short (20-rd) magazines auto-issued per Honor Guard withdrawal.')
    honor_guard_rifle_long_mag_qty  = models.PositiveSmallIntegerField(default=7, help_text='Rifle Long (30-rd) magazines auto-issued per Honor Guard withdrawal.')
    honor_guard_rifle_ammo_qty    = models.PositiveSmallIntegerField(default=210, help_text='Rifle ammunition rounds auto-issued per Honor Guard withdrawal.')
    honor_guard_bandoleer_qty     = models.PositiveSmallIntegerField(default=0,   help_text='Bandoleers auto-issued per Honor Guard withdrawal.')

    # ── Standard loadout defaults — Others ────────────────────────────────────
    others_holster_qty       = models.PositiveSmallIntegerField(default=1,   help_text='Pistol holsters auto-issued per Others withdrawal.')
    others_mag_pouch_qty     = models.PositiveSmallIntegerField(default=1,   help_text='Magazine pouches auto-issued per Others withdrawal.')
    others_pistol_mag_qty    = models.PositiveSmallIntegerField(default=4,   help_text='Pistol magazines auto-issued per Others withdrawal.')
    others_pistol_ammo_qty   = models.PositiveSmallIntegerField(default=42,  help_text='Pistol ammunition rounds auto-issued per Others withdrawal.')
    others_rifle_sling_qty   = models.PositiveSmallIntegerField(default=1,   help_text='Rifle slings auto-issued per Others withdrawal.')
    others_rifle_short_mag_qty = models.PositiveSmallIntegerField(default=7, help_text='Rifle Short (20-rd) magazines auto-issued per Others withdrawal.')
    others_rifle_long_mag_qty  = models.PositiveSmallIntegerField(default=7, help_text='Rifle Long (30-rd) magazines auto-issued per Others withdrawal.')
    others_rifle_ammo_qty    = models.PositiveSmallIntegerField(default=210, help_text='Rifle ammunition rounds auto-issued per Others withdrawal.')
    others_bandoleer_qty     = models.PositiveSmallIntegerField(default=0,   help_text='Bandoleers auto-issued per Others withdrawal.')

    # ── Standard loadout defaults — OREX ─────────────────────────────────────
    orex_holster_qty       = models.PositiveSmallIntegerField(default=1,   help_text='Pistol holsters auto-issued per OREX withdrawal.')
    orex_mag_pouch_qty     = models.PositiveSmallIntegerField(default=1,   help_text='Magazine pouches auto-issued per OREX withdrawal.')
    orex_pistol_mag_qty    = models.PositiveSmallIntegerField(default=4,   help_text='Pistol magazines auto-issued per OREX withdrawal.')
    orex_pistol_ammo_qty   = models.PositiveSmallIntegerField(default=42,  help_text='Pistol ammunition rounds auto-issued per OREX withdrawal.')
    orex_rifle_sling_qty   = models.PositiveSmallIntegerField(default=1,   help_text='Rifle slings auto-issued per OREX withdrawal.')
    orex_rifle_short_mag_qty = models.PositiveSmallIntegerField(default=7, help_text='Rifle Short (20-rd) magazines auto-issued per OREX withdrawal.')
    orex_rifle_long_mag_qty  = models.PositiveSmallIntegerField(default=7, help_text='Rifle Long (30-rd) magazines auto-issued per OREX withdrawal.')
    orex_rifle_ammo_qty    = models.PositiveSmallIntegerField(default=210, help_text='Rifle ammunition rounds auto-issued per OREX withdrawal.')
    orex_bandoleer_qty     = models.PositiveSmallIntegerField(default=0,   help_text='Bandoleers auto-issued per OREX withdrawal.')

    # ── Accessory max quantities per single withdrawal ─────────────────────────
    max_pistol_holster_qty  = models.PositiveSmallIntegerField(
        default=1, help_text='Maximum pistol holsters issuable in a single withdrawal.')
    max_magazine_pouch_qty  = models.PositiveSmallIntegerField(
        default=3, help_text='Maximum magazine pouches issuable in a single withdrawal.')
    max_rifle_sling_qty     = models.PositiveSmallIntegerField(
        default=1, help_text='Maximum rifle slings issuable in a single withdrawal.')
    max_bandoleer_qty       = models.PositiveSmallIntegerField(
        default=1, help_text='Maximum bandoleers issuable in a single withdrawal.')

    # ── Per-purpose auto TR print ─────────────────────────────────────────────
    # When True the TR print page opens automatically after saving a TR Withdrawal
    # for that purpose.
    auto_print_tr_duty_sentinel = models.BooleanField(default=False, help_text='Auto-print TR for Duty Sentinel withdrawals.')
    auto_print_tr_duty_vigil    = models.BooleanField(default=False, help_text='Auto-print TR for Duty Vigil withdrawals.')
    auto_print_tr_duty_security = models.BooleanField(default=False, help_text='Auto-print TR for Duty Security withdrawals.')
    auto_print_tr_honor_guard   = models.BooleanField(default=False, help_text='Auto-print TR for Honor Guard withdrawals.')
    auto_print_tr_others        = models.BooleanField(default=False, help_text='Auto-print TR for Others withdrawals.')
    auto_print_tr_orex          = models.BooleanField(default=False, help_text='Auto-print TR for OREX withdrawals.')

    class Meta:
        verbose_name        = "System Settings"
        verbose_name_plural = "System Settings"

    def __str__(self):
        return "System Settings"

    @classmethod
    def get(cls):
        """Return the singleton instance, seeding defaults from settings.py on first use.

        Cached for 60 s — SystemSettings changes maybe once a month; hitting the DB
        on every request (twice, from both context_processors) adds unnecessary load.
        The cache is invalidated by save() so any admin change takes effect within 60 s.
        """
        from django.core.cache import cache as _cache
        _CACHE_KEY = 'armguard_system_settings'
        cached = _cache.get(_CACHE_KEY)
        if cached is not None:
            return cached
        obj, _ = cls.objects.get_or_create(pk=1, defaults={
            'commander_name':          getattr(settings, 'ARMGUARD_COMMANDER_NAME',        ''),
            'commander_rank':          getattr(settings, 'ARMGUARD_COMMANDER_RANK',        ''),
            'commander_branch':        getattr(settings, 'ARMGUARD_COMMANDER_BRANCH',      'PAF'),
            'commander_designation':   getattr(settings, 'ARMGUARD_COMMANDER_DESIGNATION', 'Squadron Commander'),
            'armorer_branch':          getattr(settings, 'ARMGUARD_ARMORER_BRANCH',        'PAF'),
            'pistol_magazine_max_qty': getattr(settings, 'ARMGUARD_PISTOL_MAGAZINE_MAX_QTY', 4) or 4,
            'rifle_magazine_max_qty':  getattr(settings, 'ARMGUARD_RIFLE_MAGAZINE_MAX_QTY', 2) or 2,
            'mfa_required':            True,
            'password_min_length':     8,
            'password_history_count':  5,
        })
        _cache.set(_CACHE_KEY, obj, 60)
        return obj

    def save(self, *args, **kwargs):
        """Invalidate the SystemSettings cache whenever the record is updated."""
        from django.core.cache import cache as _cache
        super().save(*args, **kwargs)
        _cache.delete('armguard_system_settings')


# ── Group → UserProfile sync ─────────────────────────────────────────────────
# Maps ArmGuard role Group names to (role, per-module perm flags dict).
# System Administrator is set via is_superuser — no Group needed.

_T = True
_F = False

#                                role,              inv_v  inv_a  inv_e  inv_d  per_v  per_a  per_e  per_d  txn_v  txn_c  rep    prt    usr
_GROUP_ROLE_MAP = {
    'Armorer': (
        'Armorer',
        dict(perm_inventory_view=_T, perm_inventory_add=_F, perm_inventory_edit=_F, perm_inventory_delete=_F,
             perm_personnel_view=_T, perm_personnel_add=_F, perm_personnel_edit=_F, perm_personnel_delete=_F,
             perm_transaction_view=_T, perm_transaction_create=_T,
             perm_reports=_T, perm_print=_T, perm_users_manage=_F),
    ),
    'Administrator \u2014 View Only': (
        'Administrator — View Only',
        dict(perm_inventory_view=_T, perm_inventory_add=_F, perm_inventory_edit=_F, perm_inventory_delete=_F,
             perm_personnel_view=_T, perm_personnel_add=_F, perm_personnel_edit=_F, perm_personnel_delete=_F,
             perm_transaction_view=_T, perm_transaction_create=_F,
             perm_reports=_T, perm_print=_T, perm_users_manage=_F),
    ),
    'Administrator — Edit & Add': (
        'Administrator — Edit & Add',
        dict(perm_inventory_view=_T, perm_inventory_add=_T, perm_inventory_edit=_T, perm_inventory_delete=_F,
             perm_personnel_view=_T, perm_personnel_add=_T, perm_personnel_edit=_T, perm_personnel_delete=_F,
             perm_transaction_view=_T, perm_transaction_create=_T,
             perm_reports=_T, perm_print=_T, perm_users_manage=_T),
    ),
}

_ALL_PERM_FIELDS = [
    'perm_inventory_view', 'perm_inventory_add', 'perm_inventory_edit', 'perm_inventory_delete',
    'perm_personnel_view', 'perm_personnel_add', 'perm_personnel_edit', 'perm_personnel_delete',
    'perm_transaction_view', 'perm_transaction_create',
    'perm_reports', 'perm_print', 'perm_users_manage',
]


def _sync_profile_from_groups(user):
    """
    Sync UserProfile.role + per-module perm flags from the user's Group
    membership (or superuser status).

    Priority:
      1. is_superuser  → System Administrator, all flags True
      2. ArmGuard role Group → role + flags from _GROUP_ROLE_MAP
      If neither applies, leave the profile unchanged.
    """
    try:
        profile, _ = UserProfile.objects.get_or_create(user=user)
    except Exception:
        return

    if user.is_superuser:
        profile.role = 'System Administrator'
        for f in _ALL_PERM_FIELDS:
            setattr(profile, f, True)
        profile.save(update_fields=['role'] + _ALL_PERM_FIELDS)
        return

    group_names = set(user.groups.values_list('name', flat=True))
    for group_name, (role, perms) in _GROUP_ROLE_MAP.items():
        if group_name in group_names:
            profile.role = role
            for f, v in perms.items():
                setattr(profile, f, v)
            profile.save(update_fields=['role'] + list(perms.keys()))
            return  # first matching group wins


# on_user_groups_changed is connected lazily in UsersConfig.ready() below
# so that the User model is fully loaded before we reference its M2M through table.
def on_user_groups_changed(sender, instance, action, **kwargs):
    """Sync UserProfile whenever a User's group membership is modified."""
    if action in ('post_add', 'post_remove', 'post_clear'):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if isinstance(instance, User):
            _sync_profile_from_groups(instance)
        else:
            # instance is a Group — sync all affected users
            for user in instance.user_set.all():
                _sync_profile_from_groups(user)


# ── signal handlers ───────────────────────────────────────────────────────────

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, update_fields=None, **kwargs):
    """
    Auto-create a UserProfile whenever a new User is created.
    Also re-sync role when is_superuser is changed so that toggling superuser
    status in Django admin immediately reflects 'System Administrator' role.
    """
    if created:
        UserProfile.objects.get_or_create(user=instance)
        _sync_profile_from_groups(instance)
    elif update_fields is None or 'is_superuser' in update_fields:
        # is_superuser was (potentially) changed — re-sync role
        _sync_profile_from_groups(instance)


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    """
    G4 FIX: Update last_session_key so SingleSessionMiddleware can detect
    older concurrent sessions and forcibly log them out.
    G3 FIX: Record a LOGIN entry in the database AuditLog.
    """
    try:
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.last_session_key = request.session.session_key
        profile.save(update_fields=['last_session_key'])
    except Exception:
        logger.warning("Could not update last_session_key on login for user %s", getattr(user, 'pk', '?'))

    try:
        AuditLog.objects.create(
            user=user,
            action='LOGIN',
            model_name='User',
            object_pk=str(user.pk),
            message=f"User '{user.username}' logged in.",
            ip_address=_get_client_ip(request),
            user_agent=_get_user_agent(request),
        )
    except Exception:
        logger.warning("Failed to write LOGIN AuditLog for user %s", getattr(user, 'pk', '?'))


@receiver(user_login_failed)
def on_user_login_failed(sender, credentials, request, **kwargs):
    """
    Record every failed login attempt in AuditLog.

    Django fires this signal whenever authenticate() is called and returns None
    (wrong password, unknown username, disabled account).  It fires BEFORE the
    session is touched, so request.user is always AnonymousUser here — we record
    the attempted username from credentials instead.
    """
    attempted_username = credentials.get('username', '') if credentials else ''
    try:
        AuditLog.objects.create(
            user=None,   # not authenticated at this point
            action='LOGIN_FAILED',
            model_name='User',
            object_pk='',
            message=f"Failed login attempt for username '{attempted_username}'.",
            ip_address=_get_client_ip(request),
            user_agent=_get_user_agent(request),
        )
    except Exception:
        logger.warning("Failed to write LOGIN_FAILED AuditLog for '%s'", attempted_username)


@receiver(user_logged_out)
def on_user_logged_out(sender, request, user, **kwargs):
    """
    G4 FIX: Clear last_session_key on explicit logout.
    G3 FIX: Record a LOGOUT entry in the database AuditLog.
    """
    if user is None:
        return

    try:
        profile = user.profile
        profile.last_session_key = None
        profile.save(update_fields=['last_session_key'])
    except Exception:
        logger.warning("Could not clear last_session_key on logout for user %s", getattr(user, 'pk', '?'))

    try:
        AuditLog.objects.create(
            user=user,
            action='LOGOUT',
            model_name='User',
            object_pk=str(user.pk),
            message=f"User '{user.username}' logged out.",
            ip_address=_get_client_ip(request),
            user_agent=_get_user_agent(request),
        )
    except Exception:
        logger.warning("Failed to write LOGOUT AuditLog for user %s", getattr(user, 'pk', '?'))
