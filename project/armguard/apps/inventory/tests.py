"""
H4 FIX: Test coverage for the inventory app.

Covers:
  - Permission helper shims (_can_manage_inventory, _can_edit_delete)
  - PistolListView access and filtering
  - Aggregated COUNT stat query produces correct counts

Run with:
    python manage.py test armguard.apps.inventory
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from armguard.utils.permissions import can_manage_inventory, can_edit_delete_inventory
from .models import Pistol

User = get_user_model()


def _make_user(username, role='Armorer', is_superuser=False):
    u = User.objects.create_user(username=username, password='TestPass123!', is_superuser=is_superuser)
    if not is_superuser:
        from armguard.apps.users.models import UserProfile
        UserProfile.objects.filter(user=u).update(role=role)
        u.refresh_from_db()
        try:
            u.profile.refresh_from_db()
        except Exception:
            pass
    return u


def _login_with_otp(client, user):
    """Log the user in and mark the session as OTP-verified."""
    client.force_login(user)
    session = client.session
    session['_otp_step_done'] = True
    session.save()


def _make_pistol(serial, status='Available'):
    p = Pistol(model='Glock 17', serial_number=serial, item_status=status, item_condition='Serviceable')
    p.save()
    return p


class TestInventoryPermissions(TestCase):
    def test_armorer_can_manage(self):
        u = _make_user('arm_inv', role='Armorer')
        self.assertTrue(can_manage_inventory(u))

    def test_armorer_cannot_edit_delete(self):
        u = _make_user('arm_inv2', role='Armorer')
        self.assertFalse(can_edit_delete_inventory(u))

    def test_administrator_can_edit_delete(self):
        u = _make_user('adm_inv', role='Administrator')
        self.assertTrue(can_edit_delete_inventory(u))

    def test_superuser_can_edit_delete(self):
        u = _make_user('su_inv', is_superuser=True)
        self.assertTrue(can_edit_delete_inventory(u))


# /inventory/pistols/ — direct path avoids URL name collision with DRF router
_PISTOL_LIST_URL = '/inventory/pistols/'


class TestPistolListView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = _make_user('pistol_viewer', role='Armorer')
        _make_pistol('SN-A001', 'Available')
        _make_pistol('SN-I001', 'Issued')
        _make_pistol('SN-A002', 'Available')

    def test_unauthenticated_redirects(self):
        resp = self.client.get(_PISTOL_LIST_URL)
        self.assertIn(resp.status_code, (301, 302))

    def test_authenticated_returns_200(self):
        _login_with_otp(self.client, self.user)
        resp = self.client.get(_PISTOL_LIST_URL)
        self.assertEqual(resp.status_code, 200)

    def test_context_has_stats(self):
        _login_with_otp(self.client, self.user)
        resp = self.client.get(_PISTOL_LIST_URL)
        self.assertIn('total', resp.context)
        self.assertIn('available', resp.context)
        self.assertIn('issued', resp.context)

    def test_stats_match_db(self):
        _login_with_otp(self.client, self.user)
        resp = self.client.get(_PISTOL_LIST_URL)
        self.assertEqual(resp.context['total'], 3)
        self.assertEqual(resp.context['available'], 2)
        self.assertEqual(resp.context['issued'], 1)

    def test_search_filter(self):
        _login_with_otp(self.client, self.user)
        resp = self.client.get(_PISTOL_LIST_URL + '?q=SN-A001')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['pistols']), 1)
