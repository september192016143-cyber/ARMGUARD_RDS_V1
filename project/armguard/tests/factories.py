"""
Test factories — helper functions that create model instances with sensible
defaults.  Use these in every test module to DRY up setUp() code.
"""
from io import BytesIO
from unittest.mock import patch
from django.contrib.auth import get_user_model
from armguard.apps.inventory.models import Pistol, Rifle
from armguard.apps.personnel.models import Personnel

User = get_user_model()

_pid_counter = [1000]


def _fake_qr_buffer(*args, **kwargs):
    """Return a minimal 1×1 PNG so save() has a real file to write."""
    # Minimal valid PNG bytes (1×1 white pixel)
    PNG_1x1 = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
        b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00'
        b'\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18'
        b'\xd8H\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    return BytesIO(PNG_1x1)


def make_user(username=None, password='TestPass123!', role='Armorer',
              is_superuser=False, is_staff=False):
    """Create and return a User + UserProfile."""
    if username is None:
        username = f'user_{_pid_counter[0]}'
        _pid_counter[0] += 1
    user = User.objects.create_user(
        username=username,
        password=password,
        is_superuser=is_superuser,
        is_staff=is_staff,
    )
    user.profile.role = role
    # Apply role-specific permission presets so test users have realistic
    # permissions matching what the production group-sync signal would set.
    from armguard.apps.users.models import _GROUP_ROLE_MAP
    if role in _GROUP_ROLE_MAP:
        _, preset_perms = _GROUP_ROLE_MAP[role]
        for field, val in preset_perms.items():
            setattr(user.profile, field, val)
    user.profile.save()
    return user


def make_admin_user(username=None):
    return make_user(username=username, role='System Administrator',
                     is_superuser=True, is_staff=True)


def make_personnel(rank='SGT', first_name='Juan', last_name='Dela Cruz',
                   middle_initial='D', afsn=None, group='HAS', status='Active'):
    """Create and return a Personnel record.

    Personnel.save() generates Personnel_ID and a QR code PNG.  We mock out
    the QR generator so tests don't need filesystem access or Pillow.
    """
    if afsn is None:
        afsn = f'AF{_pid_counter[0]:06d}'
        _pid_counter[0] += 1

    # Check if already exists (handles test isolation re-use)
    existing = Personnel.objects.filter(AFSN=afsn).first()
    if existing:
        return existing

    p = Personnel(
        rank=rank,
        first_name=first_name,
        last_name=last_name,
        middle_initial=middle_initial,
        AFSN=afsn,
        group=group,
        status=status,
        squadron='',
    )
    with patch('utils.qr_generator.generate_qr_code_to_buffer', side_effect=_fake_qr_buffer):
        p.save()
    return p


def make_pistol(model='Glock 17 9mm', serial='SN-TEST-001',
                status='Available', condition='Serviceable', item_number=None):
    """Create a Pistol.  item_number is required since the item-number patch;
    a unique 4-digit value is auto-generated when not supplied."""
    if item_number is None:
        item_number = f'{_pid_counter[0]:04d}'
        _pid_counter[0] += 1
    return Pistol.objects.create(
        model=model,
        serial_number=serial,
        item_status=status,
        item_condition=condition,
        item_number=item_number,
    )


def make_rifle(model='M4 Carbine DSAR-15 5.56mm', serial='SN-RIFLE-001',
               status='Available', condition='Serviceable', item_number=None):
    """Create a Rifle.  item_number is required since the item-number patch;
    a unique 4-digit value is auto-generated when not supplied."""
    if item_number is None:
        item_number = f'{_pid_counter[0]:04d}'
        _pid_counter[0] += 1
    return Rifle.objects.create(
        model=model,
        serial_number=serial,
        item_status=status,
        item_condition=condition,
        item_number=item_number,
    )


def otp_login(client, user):
    """Force-login user and mark OTP as done in the session."""
    client.force_login(user)
    session = client.session
    session['_otp_step_done'] = True
    session.save()
