"""
ArmGuard RDS V1 — Users app models.

Models:
  UserProfile     — extends built-in User with armory role + single-session key
  AuditLog        — persistent audit trail with user-agent and integrity hash
  DeletedRecord   — soft-delete preservation: snapshot of deleted objects
"""
import hashlib
import json
from django.db import models
from django.conf import settings
from django.db.models.signals import post_save, m2m_changed
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver


ROLE_CHOICES = [
    ('System Administrator', 'System Administrator'),
    ('Administrator', 'Administrator'),
    ('Armorer', 'Armorer'),
]


def _get_user_agent(request):
    """Extract the HTTP User-Agent header (truncated to 512 chars)."""
    if request is None:
        return ''
    return request.META.get('HTTP_USER_AGENT', '')[:512]


def _get_client_ip(request):
    """Extract the real client IP, handling reverse-proxy X-Forwarded-For headers."""
    if request is None:
        return None
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
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
    # Granular permissions for the Administrator role only.
    # Superusers and System Administrators always have full access regardless of these flags.
    perm_can_add = models.BooleanField(
        default=True,
        help_text="Administrator: allowed to create new records. Has no effect on System Administrator or Armorer.",
    )
    perm_can_edit = models.BooleanField(
        default=True,
        help_text="Administrator: allowed to edit existing records. Has no effect on System Administrator or Armorer.",
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
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('OTHER', 'Other'),
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
    timestamp = models.DateTimeField(auto_now_add=True)

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


# ── Group → UserProfile sync ─────────────────────────────────────────────────
# Maps ArmGuard role Group names to (role, perm_can_add, perm_can_edit).
# Assigning a user to one of these Groups automatically sets their profile.
# System Administrator is set directly on UserProfile.role — no Group needed.

_GROUP_ROLE_MAP = {
    'Armorer':                     ('Armorer',       False, False),
    'Administrator \u2014 View Only':  ('Administrator', False, False),
    'Administrator \u2014 Edit & Add': ('Administrator', True,  True),
}


def _sync_profile_from_groups(user):
    """
    Sync UserProfile.role + perm flags from the user's Group membership
    (or superuser status).

    Priority order:
      1. is_superuser  → System Administrator (full access)
      2. ArmGuard role Group → matching role + perm flags
      If neither applies, leave the profile unchanged.
    """
    try:
        profile, _ = UserProfile.objects.get_or_create(user=user)
    except Exception:
        return

    # Superuser always maps to System Administrator regardless of Groups
    if user.is_superuser:
        profile.role          = 'System Administrator'
        profile.perm_can_add  = True
        profile.perm_can_edit = True
        profile.save(update_fields=['role', 'perm_can_add', 'perm_can_edit'])
        return

    group_names = set(user.groups.values_list('name', flat=True))

    for group_name, (role, can_add, can_edit) in _GROUP_ROLE_MAP.items():
        if group_name in group_names:
            profile.role          = role
            profile.perm_can_add  = can_add
            profile.perm_can_edit = can_edit
            profile.save(update_fields=['role', 'perm_can_add', 'perm_can_edit'])
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
        pass  # Never block a login due to profile errors.

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
        pass


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
        pass

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
        pass
