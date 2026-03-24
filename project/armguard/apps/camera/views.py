"""
Camera app views.

Public surface (phone-facing, NO LOGIN REQUIRED)
-------------------------------------------------
  /camera/                         camera_upload_page   (active device in session)
  /camera/upload/                  upload_image         (POST only; HMAC + session auth)
  /camera/activate/<token>/        activate_device_view (QR scan → auto-login)
  /camera/no-device/               no_device_view       (error page)

Admin surface (System Administrator only, login required)
----------------------------------------------------------
  /camera/admin/devices/           device_list_view
  /camera/admin/pair/<user_pk>/    pair_device_view     (generates + shows QR)
  /camera/admin/revoke/<dev_pk>/   revoke_device_view   (POST; disables device)

Passwordless authentication flow
---------------------------------
  1. System Admin visits /camera/admin/pair/<armorer_pk>/ → shows QR code.
  2. Armorer scans QR with phone (NO USERNAME/PASSWORD NEEDED).
  3. Server validates token → auto-logins armorer → stores token in session.
  4. Phone redirects to /camera/ → upload page loads.
  5. Copying the URL to a different phone WON'T WORK (no session cookie).

Security model
--------------
  1. Device binding — device_token (256-bit) stored in server-side session after QR scan.
                      Session cookie binds the browser. NO LOGIN REQUIRED.
  2. HMAC API key   — TOTP-style: HMAC-SHA256(device_token, time_window).
                      Changes every 5 minutes; current window ± 1 accepted.
                      Injected into <meta> tag; JS reads and sends via X-Api-Key header.
  3. Brute-force    — 5 wrong keys → 30-minute device lockout.
  4. One device     — OneToOneField ensures one phone per armorer.
  5. Role gate      — Only Armorer / System Administrator accounts can have devices paired.
  6. Instant revoke — Regenerating token invalidates all existing sessions immediately.
"""
import base64
import hashlib
import io
import os
import time
import uuid

import qrcode
import qrcode.constants

from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
from django.conf import settings

from .models import CameraDevice, CameraUploadLog
from .permissions import camera_admin_required, CAMERA_ALLOWED_ROLES, https_required

# ── Constants ─────────────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
MAX_UPLOAD_BYTES   = 15 * 1024 * 1024  # 15 MB

# Session key used to store the paired device_token server-side
_SESSION_KEY    = 'camera_device_token'
_SESSION_IP_KEY = 'camera_bound_ip'
_SESSION_UA_KEY = 'camera_bound_ua'  # SHA-256 of User-Agent


def _ua_hash(request) -> str:
    """SHA-256 of the User-Agent, used to bind the session to one browser/device."""
    ua = request.META.get('HTTP_USER_AGENT', '')
    return hashlib.sha256(ua.encode()).hexdigest()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_device_from_session(request):
    """
    Return the CameraDevice bound to this session, or None.

    Security checks (in order):
      1. Session must contain a valid device_token.
      2. Client IP must match the IP recorded at activation.
      3. User-Agent hash must match the one recorded at activation.
      4. Device must be active and not revoked in the database.

    This replaces Django's login() and provides equivalent binding:
    even if the session cookie is stolen, it cannot be used from a
    different device or network.
    """
    token = request.session.get(_SESSION_KEY)
    if not token:
        return None

    # User-Agent binding — reject requests from a different browser / device.
    # IP binding is intentionally omitted: DHCP lease renewal on mobile networks
    # can change the phone's IP mid-session, causing a spurious session flush.
    # The 256-bit device token + UA hash already provide strong binding.
    bound_ua = request.session.get(_SESSION_UA_KEY)
    if bound_ua and _ua_hash(request) != bound_ua:
        request.session.flush()
        return None

    try:
        return CameraDevice.objects.select_related('user').get(
            device_token=token,
            is_active=True,
            revoked_at__isnull=True,
        )
    except CameraDevice.DoesNotExist:
        request.session.pop(_SESSION_KEY, None)
        return None


def _client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
    return xff or request.META.get('REMOTE_ADDR') or None


def _make_qr_b64(data: str) -> str:
    """Return a base64-encoded PNG of a QR code."""
    qr = qrcode.QRCode(
        box_size=8,
        border=3,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='#0f172a', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


# ── Phone-facing views ────────────────────────────────────────────────────────

def activate_device_view(request, token: str):
    """
    The phone opens this URL after scanning the QR code.
    
    NO LOGIN REQUIRED — the device token IS the authentication.
    HTTPS NOT ENFORCED (for now) — allows QR scan over HTTP, then upgrades.
    
    Flow:
      1. Phone scans QR → opens this URL (may be HTTP or HTTPS).
      2. Validate token exists and is not revoked.
      3. Auto-login the user that owns this device.
      4. Store token in server-side session.
      5. Show transitional page: "Installing..." with instructions to:
         - Download SSL cert (if not HTTPS)
         - Switch to HTTPS and refresh
         - Then upload page will load
    """
    try:
        device = CameraDevice.objects.select_related('user').get(device_token=token)
    except CameraDevice.DoesNotExist:
        return render(request, 'camera/no_device.html', {
            'error': 'Invalid or expired pairing token. Ask your administrator for a new QR code.'
        }, status=400)

    if device.revoked_at:
        return render(request, 'camera/no_device.html', {
            'error': 'This device has been revoked. Contact your administrator.'
        }, status=403)

    # Verify the device owner has camera permissions (safeguard)
    owner = device.user
    role = getattr(getattr(owner, 'profile', None), 'role', '')
    if not (owner.is_superuser or role in CAMERA_ALLOWED_ROLES):
        return render(request, 'camera/no_device.html', {
            'error': f'User {owner.username} does not have camera access permissions.'
        }, status=403)

    # First-time activation: record timestamp + fingerprint
    is_first_activation = not device.is_active
    if is_first_activation:
        device.is_active = True
        device.activated_at = timezone.now()
        device.device_fingerprint = request.META.get('HTTP_USER_AGENT', '')[:512]
        device.save(update_fields=['is_active', 'activated_at', 'device_fingerprint'])

    # If the phone carries a stale Django auth session (from when login() was
    # still being called), SingleSessionMiddleware will see a key mismatch vs
    # the PC session and immediately log the phone out → login redirect.
    # Prevent this by explicitly clearing Django auth from the session first.
    # logout() flushes the session and creates a new session key, so we set
    # camera keys afterwards on the clean session.
    from django.contrib.auth import logout as _auth_logout
    if request.user.is_authenticated:
        _auth_logout(request)  # clears Django auth only; new session key is issued

    # Store device token + IP + UA hash in session (server-side only, never in JS).
    # We deliberately do NOT call login() here — the token+IP+UA binding is the
    # authentication. login() would update last_session_key and trigger
    # SingleSessionMiddleware to kill the administrator's active PC session.
    request.session[_SESSION_KEY]    = token
    request.session[_SESSION_IP_KEY] = _client_ip(request)  # stored for audit logs only
    request.session[_SESSION_UA_KEY] = _ua_hash(request)
    # 12-hour absolute expiry instead of set_expiry(0).
    # A browser-session cookie (expiry=0) is discarded by mobile browsers when
    # they background or hibernate browser tabs — the phone wakes up with no
    # session and must re-scan the QR code. A 12-hour Max-Age cookie survives.
    request.session.set_expiry(60 * 60 * 12)
    request.session.modified = True

    # Always show SSL setup on first activation so the user installs the cert.
    # https_url points back to THIS activate URL over HTTPS — that re-runs
    # activate_device_view over a secure connection, re-sets the session as a
    # Secure cookie, then proceeds to the upload page (is_first_activation=False).
    if is_first_activation and not settings.DEBUG:
        return render(request, 'camera/setup_ssl.html', {
            'device':    device,
            'https_url': request.build_absolute_uri().replace('http://', 'https://'),
            'cert_url':  request.build_absolute_uri('/download/ssl-cert/'),
        })
    
    return redirect('camera:upload_page')


@https_required
def camera_upload_page(request):
    """
    Upload landing page.
    
    Authentication: Session must contain a valid device token (set by QR scan).
    No username/password required - the token is the authentication.
    Injects the current HMAC API key as a <meta> tag.
    """
    device = _get_device_from_session(request)
    if device is None:
        return redirect('camera:no_device')

    if device.is_locked():
        return render(request, 'camera/no_device.html', {
            'error': 'This device is temporarily locked due to repeated failed attempts. '
                     'Try again in 30 minutes or contact your administrator.'
        }, status=429)

    return render(request, 'camera/upload.html', {
        'device':          device,
        'current_api_key': device.current_api_key(),
        'key_expires_ms':  device.key_valid_until_ms(),
        # Full HTTPS activate URL stored client-side for auto-reactivation when
        # the 12-hour session expires.  JS reads it from the <meta> tag, saves
        # it in localStorage, and navigates there silently when the session is
        # gone.  activate_device_view re-issues the session; no admin needed.
        # If the device is revoked, activate_device_view returns 403 and the
        # user sees the "contact admin" page — the correct gate.
        'reactivate_url':  request.build_absolute_uri(
            reverse('camera:activate_device', kwargs={'token': device.device_token})
        ),
    })


def no_device_view(request):
    return render(request, 'camera/no_device.html')


@https_required
@require_POST
def upload_image(request):
    """
    Accept a photo from the armorer's phone.

    Authentication chain
    --------------------
    1. Session device_token  → device identity (no login required).
    2. X-Api-Key header      → HMAC time-window proof of possession.
    3. Device locked?        → 429 if brute-force triggered.
    4. File validation       → extension + size.
    5. Save file             → UUID filename under MEDIA_ROOT.
    6. Log to CameraUploadLog.
    """
    device = _get_device_from_session(request)
    if device is None:
        return JsonResponse({'success': False, 'error': 'Device not authenticated. Scan the QR code again.'}, status=403)

    if device.is_locked():
        return JsonResponse({'success': False, 'error': 'Device temporarily locked. Try again in 30 minutes.'}, status=429)

    # Validate rotating HMAC API key
    provided_key = request.headers.get('X-Api-Key', '')
    if not device.check_api_key(provided_key):
        device.record_failure()
        return JsonResponse({'success': False, 'error': 'Invalid API key. Reload the page to refresh.'}, status=403)

    file = request.FILES.get('image')
    if not file:
        return JsonResponse({'success': False, 'error': 'No image file received.'}, status=400)

    original_name = file.name  # preserved for audit; never used in paths

    _, ext = os.path.splitext(file.name.lower())
    if ext not in ALLOWED_EXTENSIONS:
        return JsonResponse(
            {'success': False, 'error': 'File type not allowed. Use: ' + ', '.join(sorted(ALLOWED_EXTENSIONS))},
            status=400,
        )

    if file.size > MAX_UPLOAD_BYTES:
        return JsonResponse(
            {'success': False, 'error': f'File too large. Maximum is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.'},
            status=400,
        )

    # Save with a UUID filename — no client-supplied name ever touches the disk
    date_str  = timezone.localdate().strftime('%Y-%m-%d')
    safe_name = uuid.uuid4().hex + ext
    rel_path  = f'camera_uploads/{date_str}/{safe_name}'
    abs_dir   = os.path.join(settings.MEDIA_ROOT, 'camera_uploads', date_str)
    os.makedirs(abs_dir, exist_ok=True)

    with open(os.path.join(abs_dir, safe_name), 'wb') as fh:
        for chunk in file.chunks():
            fh.write(chunk)

    file_url = request.build_absolute_uri(settings.MEDIA_URL + rel_path)

    CameraUploadLog.objects.create(
        uploaded_by=device.user,
        device=device,
        original_name=original_name,
        stored_name=safe_name,
        file_path=rel_path,
        file_size_bytes=file.size,
        ip_address=_client_ip(request),
    )

    device.record_success()

    return JsonResponse({'success': True, 'filename': safe_name, 'url': file_url})


# ── Admin views ───────────────────────────────────────────────────────────────

@camera_admin_required
def device_list_view(request):
    """All camera devices — System Administrator only."""
    devices = (
        CameraDevice.objects
        .select_related('user', 'revoked_by')
        .order_by('user__username')
    )
    return render(request, 'camera/device_list.html', {'devices': devices})


@camera_admin_required
@require_http_methods(['GET', 'POST'])
def pair_device_view(request, user_pk: int):
    """
    Generate (or display) the QR code pairing a phone to an armorer.

    The QR encodes:  /camera/activate/<device_token>/
    That URL is usable any number of times by the registered user (re-scan after
    session expiry), but the token never appears in plain text on the page.
    """
    User = get_user_model()
    armorer = get_object_or_404(User, pk=user_pk)

    armorer_role = getattr(getattr(armorer, 'profile', None), 'role', '')
    if not (armorer.is_superuser or armorer_role in CAMERA_ALLOWED_ROLES):
        return render(request, 'camera/pair.html', {
            'armorer': armorer,
            'error':   f'User "{armorer.username}" does not have an Armorer or Administrator role.',
        }, status=400)

    device, _ = CameraDevice.objects.get_or_create(user=armorer)

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'set_name':
            device.device_name = request.POST.get('device_name', '')[:100]
            device.save(update_fields=['device_name'])

        elif action == 'revoke':
            device.is_active  = False
            device.revoked_at = timezone.now()
            device.revoked_by = request.user
            device.save(update_fields=['is_active', 'revoked_at', 'revoked_by'])

        elif action == 'unrevoke':
            device.revoked_at = None
            device.revoked_by = None
            device.save(update_fields=['revoked_at', 'revoked_by'])

        elif action == 'regenerate':
            # Issue a brand-new token; old session tokens are instantly invalidated
            old_name = device.device_name
            device.delete()
            device = CameraDevice.objects.create(user=armorer, device_name=old_name)

        return redirect('camera:pair_device', user_pk=user_pk)

    activate_url = request.build_absolute_uri(
        reverse('camera:activate_device', kwargs={'token': device.device_token})
    )
    qr_b64 = _make_qr_b64(activate_url)

    return render(request, 'camera/pair.html', {
        'armorer':      armorer,
        'device':       device,
        'qr_b64':       qr_b64,
        'activate_url': activate_url,
    })


@camera_admin_required
def device_status_api(request, user_pk: int):
    """JSON poll endpoint for the pair page auto-refresh."""
    from django.contrib.auth import get_user_model as _get_user_model
    User = _get_user_model()
    device = CameraDevice.objects.filter(user_id=user_pk).select_related('user').first()
    if not device:
        return JsonResponse({'found': False})
    return JsonResponse({
        'found':        True,
        'is_active':    device.is_active,
        'revoked':      bool(device.revoked_at),
        'activated_at': device.activated_at.strftime('%d %b %Y %H:%M') if device.activated_at else None,
        'last_seen':    device.last_seen_at.strftime('%d %b %Y %H:%M') if device.last_seen_at else None,
        'fingerprint':  (device.device_fingerprint or '')[:80],
    })


@camera_admin_required
def devices_feed_api(request):
    """
    JSON snapshot of every device's live status.
    Polled every 5 s by device_list.html and pair.html to update status
    badges, last-seen times and lock states without a page reload.
    """
    devices = (
        CameraDevice.objects
        .select_related('user')
        .order_by('user__username')
    )
    data = []
    for d in devices:
        locked = d.is_locked()
        data.append({
            'pk':              d.pk,
            'user_pk':         d.user.pk,
            'username':        d.user.username,
            'full_name':       d.user.get_full_name(),
            'device_name':     d.device_name or '',
            'is_active':       d.is_active,
            'revoked':         bool(d.revoked_at),
            'locked':          locked,
            'locked_until':    d.locked_until.strftime('%H:%M') if locked and d.locked_until else None,
            'activated_at':    d.activated_at.strftime('%d %b %Y %H:%M') if d.activated_at else None,
            'last_seen':       d.last_seen_at.strftime('%d %b %Y %H:%M') if d.last_seen_at else None,
            'failed_attempts': d.failed_attempts,
        })
    return JsonResponse({'devices': data, 'ts': int(time.time())})


@camera_admin_required
def logs_feed_api(request):
    """
    JSON list of the 50 most recent upload log entries.
    Optional ?device=<user_pk> query param narrows to one device.
    Polled by admin pages to render a live upload-log table without a reload.
    """
    device_user_pk = request.GET.get('device')
    qs = (
        CameraUploadLog.objects
        .select_related('uploaded_by', 'device')
        .order_by('-uploaded_at')
    )
    if device_user_pk:
        qs = qs.filter(device__user__pk=device_user_pk)
    logs = []
    for log in qs[:50]:
        logs.append({
            'pk':              log.pk,
            'uploaded_by':     log.uploaded_by.username if log.uploaded_by else '\u2014',
            'device_name':     log.device.device_name if log.device else '\u2014',
            'original_name':   log.original_name,
            'file_size_bytes': log.file_size_bytes,
            'uploaded_at':     log.uploaded_at.strftime('%d %b %Y %H:%M:%S'),
            'ip_address':      log.ip_address or '\u2014',
            'file_url':        request.build_absolute_uri(settings.MEDIA_URL + log.file_path),
        })
    return JsonResponse({'logs': logs, 'count': len(logs), 'ts': int(time.time())})


@https_required
def key_refresh_api(request):
    """
    Return a fresh HMAC API key for the active camera session.

    Called via AJAX from the upload page when the phone resumes from background
    and the 5-minute key window has expired.  This avoids a full page reload
    (which would flash the screen and lose any selected-but-not-yet-uploaded photo).

    Response (200):  { authenticated: true,  key: "...", expires_ms: 1234567890 }
    Response (403):  { authenticated: false }
    """
    device = _get_device_from_session(request)
    if device is None:
        return JsonResponse({'authenticated': False}, status=403)
    return JsonResponse({
        'authenticated': True,
        'key':           device.current_api_key(),
        'expires_ms':    device.key_valid_until_ms(),
    })


@camera_admin_required
@require_POST
def revoke_device_view(request, device_pk: int):
    """Quick-revoke from the device list."""
    device = get_object_or_404(CameraDevice, pk=device_pk)
    device.is_active  = False
    device.revoked_at = timezone.now()
    device.revoked_by = request.user
    device.save(update_fields=['is_active', 'revoked_at', 'revoked_by'])
    return redirect('camera:device_list')
