"""
G16-EXT: Password history validator — prevents users from reusing recent passwords.
G16-EXT2: Dynamic minimum-length validator — enforces the admin-configured minimum
           from SystemSettings instead of a hardcoded constant.

Referenced by AUTH_PASSWORD_VALIDATORS in settings/base.py.
"""
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError


class DynamicMinLengthValidator:
    """
    Enforces the password minimum-length value stored in SystemSettings
    (configurable via the System Settings page).

    Falls back to 8 characters if the DB is unavailable (e.g. during
    migrations or initial setup).  Replaces the hardcoded
    MinimumLengthValidator entry in AUTH_PASSWORD_VALIDATORS so that
    the admin-set value is actually enforced at validation time.
    """

    def validate(self, password, user=None):
        try:
            from armguard.apps.users.models import SystemSettings
            min_len = SystemSettings.get().password_min_length or 8
        except Exception:
            min_len = 8
        if len(password) < min_len:
            raise ValidationError(
                f"This password is too short. It must contain at least {min_len} character{'' if min_len == 1 else 's'}.",
                code='password_too_short',
                params={'min_length': min_len},
            )

    def get_help_text(self):
        try:
            from armguard.apps.users.models import SystemSettings
            min_len = SystemSettings.get().password_min_length or 8
        except Exception:
            min_len = 8
        return f"Your password must contain at least {min_len} character{'' if min_len == 1 else 's'}."


class PasswordHistoryValidator:
    """
    Rejects a new password if it matches any of the user's N most recent
    stored password hashes.  N is read live from SystemSettings so that
    the admin-configured value on the System Settings page is actually
    enforced at validation time.

    The history is stored in the PasswordHistory model (users app).  The
    validator is a no-op for new (unsaved) users since they have no history.
    """

    def __init__(self, history_count=5):
        self.history_count = history_count  # used as fallback only

    def validate(self, password, user=None):
        if user is None or not getattr(user, 'pk', None):
            return  # No history for unsaved users.
        try:
            from armguard.apps.users.models import SystemSettings
            history_count = SystemSettings.get().password_history_count
        except Exception:
            history_count = self.history_count  # fallback to OPTIONS value
        if history_count == 0:
            return  # history check disabled
        # Import here to avoid circular import at module load time.
        from armguard.apps.users.models import PasswordHistory
        recent = (
            PasswordHistory.objects
            .filter(user=user)
            .order_by('-created_at')[:history_count]
        )
        for record in recent:
            if check_password(password, record.password_hash):
                raise ValidationError(
                    f"You cannot reuse any of your last {history_count} passwords.",
                    code='password_too_recent',
                )

    def get_help_text(self):
        try:
            from armguard.apps.users.models import SystemSettings
            history_count = SystemSettings.get().password_history_count
        except Exception:
            history_count = self.history_count
        if history_count == 0:
            return "Password reuse history check is disabled."
        return (
            f"Your password cannot be the same as any of your last "
            f"{history_count} password{'' if history_count == 1 else 's'}."
        )
