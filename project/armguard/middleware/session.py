"""
Single-session enforcement middleware.  (G4 FIX — §3.8)

Ensures each user account has at most one active session at a time.
When a new login occurs, the user_logged_in signal updates
UserProfile.last_session_key with the new session key.
On subsequent requests from any *older* session, this middleware detects
the mismatch, forcibly logs out that session, and redirects to the login
page with an explanatory warning.
"""
from django.conf import settings
from django.contrib.auth import logout
from django.contrib import messages
from django.shortcuts import redirect


class SingleSessionMiddleware:
    """Invalidate stale sessions when the user has re-authenticated elsewhere."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            current_key = request.session.session_key
            try:
                profile = request.user.profile
                if (
                    profile.last_session_key
                    and current_key
                    and profile.last_session_key != current_key
                ):
                    logout(request)
                    messages.warning(
                        request,
                        "Your account was signed in from another location. "
                        "This session has been ended for security.",
                    )
                    return redirect(settings.LOGIN_URL)
            except Exception:
                # Missing profile or transient DB error — never block the request.
                # Log silently so the error is visible in server logs without exposing it to the user.
                import logging as _log
                _log.getLogger(__name__).debug('SingleSessionMiddleware profile lookup failed', exc_info=True)
                pass

        return self.get_response(request)
