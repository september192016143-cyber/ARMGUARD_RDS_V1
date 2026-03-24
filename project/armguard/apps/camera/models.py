import hmac as _hmac
import hashlib
import secrets
import time

from django.db import models
from django.contrib.auth import get_user_model

# ── TOTP-style rotating API key ───────────────────────────────────────────────
#
# The device_token (256-bit random, stored only in DB + QR) is the HMAC key.
# The time-window index ( floor(epoch / 300) ) is the HMAC message.
# Result: the key changes every 5 minutes automatically, zero DB writes.
# The server accepts current window ± 1 to tolerate clock drift and requests
# that straddle a window boundary.

KEY_WINDOW_SECONDS = 300  # 5-minute windows


def _generate_device_token() -> str:
    """256 bits of CSPRNG entropy as a 64-char hex string."""
    return secrets.token_hex(32)


def _compute_api_key(device_token: str, window_offset: int = 0) -> str:
    """HMAC-SHA256(device_token, time_window_index + offset)."""
    window = str(int(time.time()) // KEY_WINDOW_SECONDS + window_offset).encode()
    return _hmac.new(device_token.encode(), window, hashlib.sha256).hexdigest()


def verify_api_key(device_token: str, provided: str) -> bool:
    """Constant-time check across 3 consecutive windows (prev, cur, next)."""
    if not provided:
        return False
    for offset in (0, -1, 1):
        if _hmac.compare_digest(_compute_api_key(device_token, offset), provided):
            return True
    return False


# ── Models ────────────────────────────────────────────────────────────────────

class CameraDevice(models.Model):
    """
    Binds ONE mobile phone to ONE armorer account.

    Security controls
    -----------------
    * OneToOneField  → one phone per armorer, enforced at the database level.
    * device_token   → permanent 256-bit secret, shared once via QR code.
                       Never re-transmitted; never stored in plain browser state.
    * API key        → HMAC-SHA256(device_token, time_window): auto-rotates
                       every 5 minutes with no database writes.
    * Brute-force    → 5 consecutive bad keys locks the device for 30 minutes.
    * Revocation     → System Administrator can instantly disable any device.
    * Access gate    → Only users with role Armorer or System Administrator
                       may activate or use a device.
    """

    user = models.OneToOneField(
        get_user_model(),
        on_delete=models.CASCADE,
        related_name='camera_device',
        help_text="One registered device per armorer. Enforced at database level.",
    )
    device_token = models.CharField(
        max_length=64,
        unique=True,
        default=_generate_device_token,
        editable=False,
        help_text="Permanent 256-bit identity token. Shared once via QR. Regenerating resets pairing.",
    )
    device_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Optional label (e.g. 'Sgt. Santos — Samsung A54').",
    )
    device_fingerprint = models.CharField(
        max_length=512,
        blank=True,
        editable=False,
        help_text="HTTP User-Agent captured at first activation.",
    )
    is_active = models.BooleanField(
        default=False,
        help_text="QR has been scanned and device is not revoked.",
    )

    # ── Audit timestamps ──────────────────────────────────────────────────────
    paired_at    = models.DateTimeField(auto_now_add=True, help_text="When this record was created by an admin.")
    activated_at = models.DateTimeField(null=True, blank=True, help_text="When the armorer first scanned the QR.")
    last_seen_at = models.DateTimeField(null=True, blank=True, help_text="Last successful upload timestamp.")

    # ── Revocation ────────────────────────────────────────────────────────────
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        get_user_model(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='revoked_camera_devices',
        help_text="Administrator who revoked this device.",
    )

    # ── 30-second rotating PIN gate ───────────────────────────────────────────
    # Generated fresh by generate_pin(); shown on the PC pair page.
    # Phone must submit it via /camera/api/pin/ before the upload form unlocks.
    current_pin = models.CharField(
        max_length=6,
        blank=True,
        help_text="Current 6-digit PIN (rotates every 30 s). Empty until first generated.",
    )
    pin_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When current_pin expires and must be regenerated.",
    )

    # ── Brute-force protection ────────────────────────────────────────────────
    failed_attempts = models.PositiveSmallIntegerField(
        default=0,
        help_text="Consecutive failed API-key attempts since last success.",
    )
    locked_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Device locked until this time after 5 consecutive failures (30-minute lockout).",
    )

    class Meta:
        app_label = 'camera'
        verbose_name = 'Camera Device'
        verbose_name_plural = 'Camera Devices'
        ordering = ['user__username']

    def __str__(self):
        status = 'active' if self.is_active else ('revoked' if self.revoked_at else 'pending')
        return f"{self.user.username} — {self.device_name or 'unnamed'} [{status}]"

    # ── Security helpers ──────────────────────────────────────────────────────

    def is_locked(self) -> bool:
        from django.utils import timezone
        return bool(self.locked_until and self.locked_until > timezone.now())

    def record_failure(self) -> None:
        """Increment failure counter; lock device after 5 consecutive failures."""
        from django.utils import timezone
        from datetime import timedelta
        self.failed_attempts += 1
        if self.failed_attempts >= 5:
            self.locked_until = timezone.now() + timedelta(minutes=30)
            self.failed_attempts = 0
        self.save(update_fields=['failed_attempts', 'locked_until'])

    def record_success(self) -> None:
        """Reset failure counter and update last-seen timestamp."""
        from django.utils import timezone
        self.failed_attempts = 0
        self.locked_until = None
        self.last_seen_at = timezone.now()
        self.save(update_fields=['failed_attempts', 'locked_until', 'last_seen_at'])

    def current_api_key(self) -> str:
        """Compute the HMAC API key for the current 5-minute window."""
        return _compute_api_key(self.device_token)

    def key_valid_until_ms(self) -> int:
        """Unix epoch milliseconds when the current key window ends (for JS timer)."""
        now = int(time.time())
        window_end = ((now // KEY_WINDOW_SECONDS) + 1) * KEY_WINDOW_SECONDS
        return window_end * 1000

    def check_api_key(self, provided: str) -> bool:
        return verify_api_key(self.device_token, provided)

    # ── PIN helpers ───────────────────────────────────────────────────────────

    def get_or_refresh_pin(self):
        """
        Return (pin, expires_at_ms).

        If the current PIN is still valid, return it unchanged.
        Otherwise generate a new 6-digit PIN valid for 30 seconds.
        Saves to DB only when a new PIN is generated.
        """
        from django.utils import timezone
        from datetime import timedelta
        now = timezone.now()
        if self.current_pin and self.pin_expires_at and self.pin_expires_at > now:
            return self.current_pin, int(self.pin_expires_at.timestamp() * 1000)
        # Generate new PIN
        new_pin = '{:06d}'.format(secrets.randbelow(1_000_000))
        expires = now + timedelta(seconds=30)
        self.current_pin   = new_pin
        self.pin_expires_at = expires
        self.save(update_fields=['current_pin', 'pin_expires_at'])
        return new_pin, int(expires.timestamp() * 1000)

    def verify_pin(self, provided: str) -> bool:
        """Constant-time comparison against the current valid PIN."""
        from django.utils import timezone
        import hmac as _hmac_mod
        if not self.current_pin or not provided:
            return False
        if self.pin_expires_at and self.pin_expires_at < timezone.now():
            return False  # expired
        return _hmac_mod.compare_digest(self.current_pin, provided.strip())


class CameraUploadLog(models.Model):
    """
    Records every image uploaded through the Camera Upload feature.

    Fields
    ------
    uploaded_by     : the logged-in user who submitted the upload.
    original_name   : the filename as reported by the client device (for reference only).
    stored_name     : the UUID-based filename actually saved to disk.
    file_path       : relative path under MEDIA_ROOT (e.g. camera_uploads/2026-03-23/<uuid>.jpg).
    file_size_bytes : size of the uploaded file in bytes.
    uploaded_at     : timestamp of the upload (auto-set).
    ip_address      : client IP address at time of upload.
    notes           : optional free-text note added by the uploader.
    """

    uploaded_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='camera_uploads',
    )
    device = models.ForeignKey(
        CameraDevice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='upload_logs',
        help_text="The paired device that performed this upload.",
    )
    original_name   = models.CharField(max_length=255, blank=True)
    stored_name     = models.CharField(max_length=255)
    file_path       = models.CharField(max_length=512)
    file_size_bytes = models.PositiveIntegerField(default=0)
    uploaded_at     = models.DateTimeField(auto_now_add=True)
    ip_address      = models.GenericIPAddressField(null=True, blank=True)
    notes           = models.TextField(blank=True)

    class Meta:
        app_label = 'camera'
        ordering = ['-uploaded_at']
        verbose_name = 'Camera Upload Log'
        verbose_name_plural = 'Camera Upload Logs'

    def __str__(self):
        user = self.uploaded_by.username if self.uploaded_by else 'anonymous'
        return f'{self.stored_name} by {user} at {self.uploaded_at:%Y-%m-%d %H:%M}'

