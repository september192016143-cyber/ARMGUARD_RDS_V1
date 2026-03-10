"""
H4 FIX: Test coverage for the dashboard app.

Covers:
  - DashboardView authentication guard
  - View returns 200 with expected context keys for authenticated users

Run with:
    python manage.py test armguard.apps.dashboard
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


def _login_with_otp(client, user):
    """Log the user in and mark the session as OTP-verified."""
    client.force_login(user)
    session = client.session
    session['_otp_step_done'] = True
    session.save()


class TestDashboardView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='dashuser', password='TestPass123!')

    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertIn(resp.status_code, (301, 302))

    def test_authenticated_returns_200(self):
        _login_with_otp(self.client, self.user)
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_context_has_personnel_stats(self):
        _login_with_otp(self.client, self.user)
        resp = self.client.get(reverse('dashboard'))
        self.assertIn('total_pistols', resp.context)
        self.assertIn('total_rifles', resp.context)

    def test_context_has_recent_transactions(self):
        _login_with_otp(self.client, self.user)
        resp = self.client.get(reverse('dashboard'))
        self.assertIn('total_transactions', resp.context)
        self.assertIn('inventory_rows', resp.context)
