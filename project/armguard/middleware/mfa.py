"""
G15 FIX: Middleware that enforces OTP verification after every successful password login.

When OTPMiddleware (django-otp) is active it sets request.user.is_verified()
to True only once the TOTP token has been checked in the current session.
This middleware redirects authenticated-but-unverified users to the OTP
verification page for every protected request, so it is impossible to reach
any application URL without completing the two-factor step.

Bypass list (no OTP check):
  • The login page itself
  • All /accounts/otp/* pages (setup + verify)
  • The logout endpoint (so a half-authenticated user can always cancel)
  • robots.txt / security.txt
  • /api/ (API clients use token auth, not session OTP)
  • Django static files and media
"""
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

_OTP_BYPASS_PREFIXES = (
    '/accounts/login',
    '/accounts/logout',
    '/accounts/otp',
    '/robots.txt',
    '/.well-known',
    '/download/ssl-cert/',
    '/download/ssl-cert-status/',
    # NOTE: '/api/' is intentionally NOT in this list — see _is_bypass() below.
    settings.STATIC_URL,
    settings.MEDIA_URL,
    f'/{settings.ADMIN_URL}/',   # admin has its own access control
)


class OTPRequiredMiddleware:
    """Force OTP step for every authenticated session that has not yet passed TOTP."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Must be authenticated (password correct) but not yet OTP-verified.
        if (
            request.user.is_authenticated
            and not self._is_otp_verified(request)
            and not self._is_bypass(request.path, request)
        ):
            verify_url = reverse('otp-verify')
            next_param = request.get_full_path()
            return redirect(f'{verify_url}?next={next_param}')

        return self.get_response(request)

    @staticmethod
    def _is_otp_verified(request):
        """
        Returns True when the user has completed the OTP step this session.

        H2 FIX (fail-CLOSED): Previously `except Exception: return True` meant
        any DB error silently disabled MFA.  Now DB errors return False — the
        user is redirected to verify rather than let through unauthenticated.

        H3 FIX (session cache): Device existence is stored in the session after
        the first check so subsequent requests on the same session make zero
        extra DB queries for the OTP device lookup.

        django-otp sets request.user.is_verified() once login() is called
        with a verified device (via django_otp.login()).

        The session key '_otp_step_done' is a boolean set by OTPVerifyView
        (and by the test helper _login_with_otp) to bypass the is_verified()
        check without requiring a live TOTP device.  This allows test clients
        that use force_login to reach authenticated views without setting up
        a full OTP device.
        """
        # Fast path: OTP step explicitly completed this session (set by
        # OTPVerifyView.post() after a successful token match, or by the
        # _login_with_otp test helper).
        if request.session.get('_otp_step_done'):
            return True

        SESSION_KEY = '_otp_device_confirmed'

        # Use session-cached "has device" result (0 DB queries on repeat requests).
        if SESSION_KEY in request.session:
            has_device = request.session[SESSION_KEY]
        else:
            # Slow path (first request this session): query the DB.
            try:
                from django_otp.plugins.otp_totp.models import TOTPDevice
                from django_otp.plugins.otp_static.models import StaticDevice
                has_device = (
                    TOTPDevice.objects.filter(user=request.user, confirmed=True).exists()
                    or StaticDevice.objects.filter(user=request.user, confirmed=True).exists()
                )
            except Exception:
                # H2 FIX: Fail CLOSED — DB error means we cannot confirm device
                # presence, so the safe choice is to redirect to verify (not let through).
                return False
            # Cache the result for this session.
            request.session[SESSION_KEY] = has_device

        if not has_device:
            # No device → redirect to setup (handled by _is_bypass 'otp-setup').
            return request.path.startswith('/accounts/otp/setup')

        return request.user.is_verified()

    @staticmethod
    def _is_bypass(path, request=None):
        # API paths: only bypass OTP for headless token-auth clients.
        # Browser/session requests to /api/ still require a completed OTP step.
        # This prevents password-only sessions from accessing the API without MFA.
        if path.startswith('/api/'):
            auth = (request.META.get('HTTP_AUTHORIZATION', '') if request else '')
            return auth.startswith('Token ') or auth.startswith('Bearer ')
        return any(path.startswith(p) for p in _OTP_BYPASS_PREFIXES)
