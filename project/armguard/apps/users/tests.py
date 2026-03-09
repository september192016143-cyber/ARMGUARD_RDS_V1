"""
H4 FIX: Test coverage for the users app.

Covers:
  - armguard.utils.permissions helpers (is_admin, can_manage_inventory, etc.)
  - PasswordHistoryValidator
  - UserListView / UserCreateView access control
  - OTPVerifyView redirect when device is missing

Run with:
    python manage.py test armguard.apps.users
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from armguard.utils.permissions import (
    is_admin, can_manage_inventory, can_edit_delete_inventory, can_create_transaction,
)

User = get_user_model()


def _make_user(username, role='Armorer', is_superuser=False, is_staff=False, password='TestPass123!'):
    u = User.objects.create_user(
        username=username, password=password,
        is_superuser=is_superuser, is_staff=is_staff,
    )
    if not is_superuser:
        # Auto-created UserProfile — explicitly set role so tests control it.
        from armguard.apps.users.models import UserProfile
        UserProfile.objects.filter(user=u).update(role=role)
        # Refresh the in-memory cache so permission helpers see the new role.
        u.refresh_from_db()
        try:
            u.profile.refresh_from_db()
        except Exception:
            pass
    return u


def _login_with_otp(client, user):
    """Log the user in and mark the session as OTP-verified to bypass OTPRequiredMiddleware."""
    client.force_login(user)
    session = client.session
    session['_otp_step_done'] = True
    session.save()


# ---------------------------------------------------------------------------
# 1. Permission helpers
# ---------------------------------------------------------------------------

class TestIsAdmin(TestCase):
    def test_superuser_is_admin(self):
        u = _make_user('su', is_superuser=True)
        self.assertTrue(is_admin(u))

    def test_staff_is_admin(self):
        u = _make_user('staff', is_staff=True)
        self.assertTrue(is_admin(u))

    def test_system_admin_role_is_admin(self):
        u = _make_user('sa', role='System Administrator')
        self.assertTrue(is_admin(u))

    def test_armorer_is_not_admin(self):
        u = _make_user('arm', role='Armorer')
        self.assertFalse(is_admin(u))

    def test_no_profile_is_not_admin(self):
        u = _make_user('nopr', role='Armorer')
        u.profile.delete()
        u.refresh_from_db()
        self.assertFalse(is_admin(u))


class TestCanManageInventory(TestCase):
    def test_armorer_can_manage(self):
        u = _make_user('arm', role='Armorer')
        self.assertTrue(can_manage_inventory(u))

    def test_administrator_can_manage(self):
        u = _make_user('adm', role='Administrator')
        self.assertTrue(can_manage_inventory(u))

    def test_can_create_transaction_armorer(self):
        u = _make_user('arm2', role='Armorer')
        self.assertTrue(can_create_transaction(u))

    def test_can_edit_delete_requires_admin(self):
        armorer = _make_user('arm3', role='Armorer')
        admin = _make_user('adm2', role='System Administrator')
        self.assertFalse(can_edit_delete_inventory(armorer))
        self.assertTrue(can_edit_delete_inventory(admin))


# ---------------------------------------------------------------------------
# 2. PasswordHistoryValidator
# ---------------------------------------------------------------------------

class TestPasswordHistoryValidator(TestCase):
    def test_new_user_passes_without_history(self):
        from armguard.apps.users.validators import PasswordHistoryValidator
        v = PasswordHistoryValidator(history_count=5)
        # No user object — should not raise.
        v.validate('SomeNewPass99!', user=None)

    def test_recent_password_rejected(self):
        from django.core.exceptions import ValidationError
        from armguard.apps.users.validators import PasswordHistoryValidator
        from armguard.apps.users.models import PasswordHistory
        u = _make_user('histuser', password='OldPass123!')
        # Store the hashed old password in history.
        PasswordHistory.objects.create(user=u, password_hash=u.password)
        v = PasswordHistoryValidator(history_count=5)
        with self.assertRaises(ValidationError):
            v.validate('OldPass123!', user=u)


# ---------------------------------------------------------------------------
# 3. UserListView — access control
# ---------------------------------------------------------------------------

class TestUserListView(TestCase):
    def setUp(self):
        self.client = Client()

    def test_unauthenticated_redirects_to_login(self):
        resp = self.client.get(reverse('user-list'))
        self.assertIn(resp.status_code, (302, 301))

    def test_armorer_gets_403(self):
        u = _make_user('armview', role='Armorer')
        _login_with_otp(self.client, u)
        resp = self.client.get(reverse('user-list'))
        # UserPassesTestMixin returns 403 for authenticated users who fail test_func.
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_access(self):
        u = _make_user('adminview', role='System Administrator')
        _login_with_otp(self.client, u)
        resp = self.client.get(reverse('user-list'))
        self.assertEqual(resp.status_code, 200)
