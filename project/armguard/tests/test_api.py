"""
Tests for armguard/apps/api/ (DRF REST endpoints).
Verifies authentication requirements, response structure, and access controls.
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from armguard.tests.factories import make_user, make_admin_user, make_pistol, make_rifle, otp_login


class TestPistolAPIList(TestCase):
    """GET /api/v1/pistols/ requires a logged-in session."""

    def setUp(self):
        self.client = APIClient()
        # PistolViewSet uses permissions.IsAdminUser → requires is_staff=True.
        self.user = make_user(username='api_p_user', role='Armorer', is_staff=True)
        make_pistol(serial='API-P-001')

    def test_anonymous_gets_403(self):
        resp = self.client.get(reverse('api:pistol-list'))
        # DRF returns 403 (not 401) when session auth is the only backend and no
        # WWW-Authenticate challenge is set.
        self.assertIn(resp.status_code, (401, 403))

    def test_auth_user_gets_200(self):
        self.client.force_login(self.user)
        session = self.client.session
        session['_otp_step_done'] = True
        session.save()
        resp = self.client.get(reverse('api:pistol-list'))
        self.assertEqual(resp.status_code, 200)

    def test_response_has_results_key(self):
        """DRF pagination wraps results in {"count": N, "results": [...]}."""
        self.client.force_login(self.user)
        session = self.client.session
        session['_otp_step_done'] = True
        session.save()
        resp = self.client.get(reverse('api:pistol-list'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # Either paginated (has 'results') or plain list
        self.assertTrue('results' in data or isinstance(data, list))


class TestRifleAPIList(TestCase):
    def setUp(self):
        self.client = APIClient()
        # RifleViewSet uses permissions.IsAdminUser → requires is_staff=True.
        self.user = make_user(username='api_r_user', role='Armorer', is_staff=True)
        make_rifle(serial='API-R-001')

    def test_anonymous_gets_403(self):
        resp = self.client.get(reverse('api:rifle-list'))
        self.assertIn(resp.status_code, (401, 403))

    def test_auth_user_gets_200(self):
        self.client.force_login(self.user)
        session = self.client.session
        session['_otp_step_done'] = True
        session.save()
        resp = self.client.get(reverse('api:rifle-list'))
        self.assertEqual(resp.status_code, 200)


class TestPersonnelAPIRequiresStaff(TestCase):
    """Personnel API is restricted to is_staff=True (contains military PII)."""

    def setUp(self):
        self.client = APIClient()
        self.armorer = make_user(username='api_pers_arm', role='Armorer')
        self.admin = make_admin_user(username='api_pers_admin')

    def test_non_staff_armorer_gets_403(self):
        self.client.force_login(self.armorer)
        session = self.client.session
        session['_otp_step_done'] = True
        session.save()
        resp = self.client.get(reverse('api:personnel-list'))
        self.assertEqual(resp.status_code, 403)

    def test_staff_admin_gets_200(self):
        self.client.force_login(self.admin)
        session = self.client.session
        session['_otp_step_done'] = True
        session.save()
        resp = self.client.get(reverse('api:personnel-list'))
        self.assertEqual(resp.status_code, 200)


class TestTransactionAPIRequiresStaff(TestCase):
    """Transaction API is restricted to is_staff=True."""

    def setUp(self):
        self.client = APIClient()
        self.armorer = make_user(username='api_txn_arm', role='Armorer')
        self.admin = make_admin_user(username='api_txn_admin')

    def test_non_staff_armorer_gets_403(self):
        self.client.force_login(self.armorer)
        session = self.client.session
        session['_otp_step_done'] = True
        session.save()
        resp = self.client.get(reverse('api:transaction-list'))
        self.assertEqual(resp.status_code, 403)

    def test_staff_admin_gets_200(self):
        self.client.force_login(self.admin)
        session = self.client.session
        session['_otp_step_done'] = True
        session.save()
        resp = self.client.get(reverse('api:transaction-list'))
        self.assertEqual(resp.status_code, 200)


class TestLastModifiedEndpoint(TestCase):
    """GET /api/v1/last-modified/ returns a JSON object with a 'last_modified' key."""

    def setUp(self):
        self.client = APIClient()
        self.user = make_user(username='api_lm_user', role='Armorer')

    def test_anonymous_gets_403(self):
        resp = self.client.get(reverse('api:api-last-modified'))
        self.assertIn(resp.status_code, (401, 403))

    def test_auth_user_gets_json_with_last_modified(self):
        self.client.force_login(self.user)
        session = self.client.session
        session['_otp_step_done'] = True
        session.save()
        resp = self.client.get(reverse('api:api-last-modified'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('last_modified', data)
