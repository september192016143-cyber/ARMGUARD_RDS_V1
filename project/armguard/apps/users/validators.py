"""
G16-EXT: Password history validator — prevents users from reusing recent passwords.

Referenced by AUTH_PASSWORD_VALIDATORS in settings/base.py.
"""
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError


class PasswordHistoryValidator:
    """
    Rejects a new password if it matches any of the user's N most recent
    stored password hashes (default: last 5).

    The history is stored in the PasswordHistory model (users app).  The
    validator is a no-op for new (unsaved) users since they have no history.
    """

    def __init__(self, history_count=5):
        self.history_count = history_count

    def validate(self, password, user=None):
        if user is None or not getattr(user, 'pk', None):
            return  # No history for unsaved users.
        # Import here to avoid circular import at module load time.
        from armguard.apps.users.models import PasswordHistory
        recent = (
            PasswordHistory.objects
            .filter(user=user)
            .order_by('-created_at')[:self.history_count]
        )
        for record in recent:
            if check_password(password, record.password_hash):
                raise ValidationError(
                    f"You cannot reuse any of your last {self.history_count} passwords.",
                    code='password_too_recent',
                )

    def get_help_text(self):
        return (
            f"Your password cannot be the same as any of your last "
            f"{self.history_count} passwords."
        )
