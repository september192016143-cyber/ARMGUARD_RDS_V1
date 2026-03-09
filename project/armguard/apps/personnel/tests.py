"""
H4 FIX: Test coverage for the personnel app.

Covers:
  - PersonnelListView authentication guard
  - Personnel model string representation

Run with:
    python manage.py test armguard.apps.personnel
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from .models import Personnel

User = get_user_model()


def _make_personnel(sid='P-TST-001', afsn='9990001'):
    return Personnel.objects.create(
        Personnel_ID=sid,
        rank='AM',
        first_name='Test',
        last_name='Pilot',
        middle_initial='T',
        AFSN=afsn,
        group='HAS',
        squadron='1SG',
        status='Active',
    )


# /personnel/ — direct path avoids URL name collision with DRF router
_PERSONNEL_LIST_URL = '/personnel/'


def _login_with_otp(client, user):
    """Log the user in and mark the session as OTP-verified."""
    client.force_login(user)
    session = client.session
    session['_otp_step_done'] = True
    session.save()


class TestPersonnelListView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='pview', password='TestPass123!')

    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(_PERSONNEL_LIST_URL)
        self.assertIn(resp.status_code, (301, 302))

    def test_authenticated_can_list(self):
        _login_with_otp(self.client, self.user)
        resp = self.client.get(_PERSONNEL_LIST_URL)
        self.assertEqual(resp.status_code, 200)


class TestPersonnelModel(TestCase):
    def test_get_display_str_returns_string(self):
        p = _make_personnel()
        s = p.get_display_str()
        self.assertIsInstance(s, str)
        self.assertIn('AM', s)
        self.assertIn('Test', s)
