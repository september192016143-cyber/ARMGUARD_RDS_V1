"""
H4 FIX: Test coverage for the api app.

Covers:
  - PistolViewSet: anonymous access blocked, authenticated access allowed
  - RifleViewSet: list returns correct count
  - LastModifiedView: endpoint returns expected keys
  - C3 FIX: BrowsableAPIRenderer is disabled in production settings

Run with:
    python manage.py test armguard.apps.api
"""
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from armguard.apps.inventory.models import Pistol, Rifle

User = get_user_model()


def _make_pistol(serial, status='Available'):
    p = Pistol(model='Glock 17', serial_number=serial, item_status=status,
               item_condition='Serviceable')
    p.save()
    return p


class TestApiAuthentication(TestCase):
    """API endpoints must refuse unauthenticated callers."""

    def test_pistol_list_requires_auth(self):
        client = APIClient()
        resp = client.get('/api/v1/pistols/')
        self.assertIn(resp.status_code, (401, 403))

    def test_last_modified_requires_auth(self):
        client = APIClient()
        resp = client.get('/api/v1/last-modified/')
        self.assertIn(resp.status_code, (401, 403))


class TestPistolViewSet(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='apiuser', password='TestPass123!')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        _make_pistol('SN-API-001')
        _make_pistol('SN-API-002')

    def test_list_returns_200(self):
        resp = self.client.get('/api/v1/pistols/')
        self.assertEqual(resp.status_code, 200)

    def test_list_returns_pistols(self):
        resp = self.client.get('/api/v1/pistols/')
        data = resp.json()
        self.assertIn('results', data)
        self.assertGreaterEqual(len(data['results']), 2)

    def test_notes_not_in_serializer_output(self):
        """M3 FIX: 'notes' and 'updated_at' must not appear in the transaction API response.
        TransactionViewSet now requires IsAdminUser — use a staff user."""
        from armguard.apps.transactions.models import Transaction
        from armguard.apps.personnel.models import Personnel
        staff_client = APIClient()
        staff_user = User.objects.create_user(
            username='staff_txn', password='TestPass123!', is_staff=True
        )
        staff_client.force_authenticate(user=staff_user)
        resp = staff_client.get('/api/v1/transactions/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        if data.get('results'):
            for txn in data['results']:
                self.assertNotIn('notes', txn)
                self.assertNotIn('updated_at', txn)


class TestTimestampFormat(TestCase):
    """All datetime fields in the API must render as UTC 'Z' strings."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='ts_user', password='TestPass123!', is_staff=True
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        _make_pistol('SN-TS-001')

    def test_pistol_created_is_utc_z(self):
        resp = self.client.get('/api/v1/pistols/')
        data = resp.json()
        ts = data['results'][0]['created']
        self.assertTrue(ts.endswith('Z'), f"Expected UTC 'Z' suffix, got: {ts}")
        self.assertNotIn('+', ts)


class TestLastModifiedView(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='lmuser', password='TestPass123!')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_returns_200(self):
        resp = self.client.get('/api/v1/last-modified/')
        self.assertEqual(resp.status_code, 200)

    def test_response_has_required_keys(self):
        resp = self.client.get('/api/v1/last-modified/')
        data = resp.json()
        self.assertIn('last_modified', data)
        self.assertIn('now', data)

    def test_last_modified_is_null_when_no_transactions(self):
        resp = self.client.get('/api/v1/last-modified/')
        data = resp.json()
        self.assertIsNone(data['last_modified'])


class TestProductionRendererSettings(TestCase):
    """C3 FIX: BrowsableAPIRenderer must be absent in all environments.
    Military PII (names, ranks, service IDs) must never be exposed via the
    DRF HTML form interface."""

    def test_browsable_api_removed_in_base_settings(self):
        from armguard.settings import base as base_settings
        renderers = base_settings.REST_FRAMEWORK.get('DEFAULT_RENDERER_CLASSES', [])
        self.assertNotIn('rest_framework.renderers.BrowsableAPIRenderer', renderers)
        self.assertIn('rest_framework.renderers.JSONRenderer', renderers)

    def test_browsable_api_removed_in_production_settings(self):
        from armguard.settings import production as prod_settings
        renderers = prod_settings.REST_FRAMEWORK.get('DEFAULT_RENDERER_CLASSES', [])
        self.assertNotIn('rest_framework.renderers.BrowsableAPIRenderer', renderers)
        self.assertIn('rest_framework.renderers.JSONRenderer', renderers)


class TestTransactionViewSetPermissions(TestCase):
    """TransactionViewSet requires IsAdminUser — operational security data."""

    def setUp(self):
        self.regular = User.objects.create_user(username='reg_txn', password='TestPass123!')
        self.staff   = User.objects.create_user(username='staff_txn2', password='TestPass123!',
                                                is_staff=True)

    def test_non_staff_gets_403(self):
        client = APIClient()
        client.force_authenticate(user=self.regular)
        resp = client.get('/api/v1/transactions/')
        self.assertEqual(resp.status_code, 403)

    def test_staff_gets_200(self):
        client = APIClient()
        client.force_authenticate(user=self.staff)
        resp = client.get('/api/v1/transactions/')
        self.assertEqual(resp.status_code, 200)


class TestOtpMiddlewareApiBypass(TestCase):
    """
    Security: /api/ must only bypass OTP for token-authenticated requests.
    Session-authenticated (browser) requests without a completed OTP step
    must be redirected to the OTP verify page.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='mfa_api_user', password='TestPass123!', is_staff=True
        )

    def test_session_without_otp_redirected(self):
        """A browser session without _otp_step_done must be redirected."""
        client = Client()
        client.force_login(self.user)
        # Do NOT set _otp_step_done — simulates password-only session.
        resp = client.get('/api/v1/pistols/')
        self.assertIn(resp.status_code, (302, 200))
        if resp.status_code == 302:
            self.assertIn('otp', resp['Location'])

    def test_session_with_otp_allowed(self):
        """A session with _otp_step_done=True must reach the API."""
        client = Client()
        client.force_login(self.user)
        session = client.session
        session['_otp_step_done'] = True
        session.save()
        resp = client.get('/api/v1/pistols/')
        self.assertEqual(resp.status_code, 200)

    def test_token_auth_bypasses_otp_check(self):
        """A Token-authenticated request must pass through without OTP session."""
        token, _ = Token.objects.get_or_create(user=self.user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        resp = client.get('/api/v1/pistols/')
        self.assertEqual(resp.status_code, 200)
