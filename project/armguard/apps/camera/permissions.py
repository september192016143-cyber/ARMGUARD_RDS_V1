"""
Camera app access control.

Three levels of restriction:

  camera_role_required   — login + role must be Armorer or System Administrator.
  camera_admin_required  — login + role must be System Administrator (or superuser).
  https_required         — reject HTTP requests; force HTTPS for camera endpoints.

All are plain function decorators compatible with Django's FBV pattern.
"""
import functools

from django.conf import settings
from django.http import HttpResponseForbidden, HttpResponseBadRequest
from django.shortcuts import redirect

# Roles permitted to use the camera upload feature.
CAMERA_ALLOWED_ROLES = frozenset({'System Administrator', 'Armorer'})


def https_required(view_func):
    """
    Decorator: reject non-HTTPS requests to camera endpoints.
    
    CRITICAL for security: without HTTPS, all traffic (session cookies,
    HMAC keys, uploaded images) travels in PLAINTEXT over WiFi.
    
    An attacker on the same network could:
      - Steal the device_token from the QR scan URL
      - Hijack the sessionid cookie
      - Replay HMAC API keys
      - Read uploaded photos
      
    This decorator enforces encryption at the application layer even if
    SECURE_SSL_REDIRECT is not enabled globally.
    """
    @functools.wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        # Allow HTTP only in DEBUG mode (local development)
        if settings.DEBUG:
            return view_func(request, *args, **kwargs)
        
        # Check if request came over HTTPS
        is_secure = (
            request.is_secure() or
            request.META.get('HTTP_X_FORWARDED_PROTO') == 'https'
        )
        
        if not is_secure:
            return HttpResponseBadRequest(
                b"<h2>HTTPS Required</h2>"
                b"<p>Camera endpoints require an encrypted connection (HTTPS) for security.</p>"
                b"<p>Please access this page via <code>https://</code> instead of <code>http://</code>.</p>"
            )
        
        return view_func(request, *args, **kwargs)
    return _wrapped


def _has_camera_role(user) -> bool:
    """Return True if the user carries an allowed role (or is a superuser)."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    try:
        return user.profile.role in CAMERA_ALLOWED_ROLES
    except Exception:
        return False


def _is_camera_admin(user) -> bool:
    """Return True if the user is a System Administrator or superuser."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    try:
        return user.profile.role == 'System Administrator'
    except Exception:
        return False


def camera_role_required(view_func):
    """
    Decorator: allow only Armorer and System Administrator (+ superuser).
    Unauthenticated users are redirected to LOGIN_URL.
    Wrong-role users receive HTTP 403.
    """
    @functools.wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")
        if not _has_camera_role(request.user):
            return HttpResponseForbidden(
                b"<h2>Access Denied</h2>"
                b"<p>Camera access is restricted to Armorers and System Administrators.</p>"
            )
        return view_func(request, *args, **kwargs)
    return _wrapped


def camera_admin_required(view_func):
    """
    Decorator: allow only System Administrator (+ superuser).
    Used for device-pairing and revocation views that must never be
    accessible to regular Armorers.
    """
    @functools.wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")
        if not _is_camera_admin(request.user):
            return HttpResponseForbidden(
                b"<h2>Access Denied</h2>"
                b"<p>Camera device management is restricted to System Administrators.</p>"
            )
        return view_func(request, *args, **kwargs)
    return _wrapped


# ── Public helpers — import these in views / context_processors ───────────────

def is_camera_admin(user) -> bool:
    """Return True if user is a System Administrator or superuser."""
    return _is_camera_admin(user)


def has_camera_role(user) -> bool:
    """Return True if user has any camera-permitted role (Armorer or System Administrator)."""
    return _has_camera_role(user)
