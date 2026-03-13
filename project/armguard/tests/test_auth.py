"""
Tests for authentication: login, logout, OTP flow, rate limiting, password policy.
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from armguard.tests.factories import make_user, otp_login

User = get_user_model()


class TestLoginView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user(username='logintest', password='TestPass123!')
        self.url = reverse('login')

    def test_get_renders_login_form(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'registration/login.html')

    def test_valid_credentials_redirect(self):
        resp = self.client.post(self.url, {'username': 'logintest', 'password': 'TestPass123!'})
        # Should redirect (either to OTP setup/verify or dashboard)
        self.assertIn(resp.status_code, (301, 302))

    def test_invalid_credentials_returns_200(self):
        resp = self.client.post(self.url, {'username': 'logintest', 'password': 'wrongpassword'})
        self.assertEqual(resp.status_code, 200)

    def test_anonymous_dashboard_redirects_to_login(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertIn(resp.status_code, (301, 302))
        self.assertIn('/accounts/login/', resp['Location'])


class TestLogoutView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user(username='logouttest')

    def test_post_logout_redirects(self):
        otp_login(self.client, self.user)
        resp = self.client.post(reverse('logout'))
        self.assertIn(resp.status_code, (301, 302))

    def test_get_logout_not_allowed(self):
        """Logout must be POST only (CSRF protection)."""
        otp_login(self.client, self.user)
        resp = self.client.get(reverse('logout'))
        # GET should redirect or 405, not log out silently
        self.assertIn(resp.status_code, (301, 302, 405))


class TestOTPSetupView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user(username='otpsetupuser')
        self.url = reverse('otp-setup')

    def test_authenticated_no_otp_redirects_to_setup(self):
        """User without OTP device should be redirected to OTP setup."""
        self.client.force_login(self.user)
        resp = self.client.get(reverse('dashboard'))
        self.assertIn(resp.status_code, (301, 302))

    def test_otp_setup_page_renders(self):
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'registration/otp_setup.html')


class TestOTPVerifyView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user(username='otpverifyuser')

    def test_verify_page_renders_for_unenrolled(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('otp-setup'))
        self.assertEqual(resp.status_code, 200)

    def test_wrong_otp_returns_error(self):
        from django_otp.plugins.otp_totp.models import TOTPDevice
        device = TOTPDevice.objects.create(user=self.user, confirmed=True, name='default')
        self.client.force_login(self.user)
        resp = self.client.post(reverse('otp-verify'), {'token': '000000'})
        # Should re-render the form with an error, not redirect to dashboard
        self.assertNotEqual(resp.get('Location', ''), reverse('dashboard'))
        device.delete()


class TestPasswordPolicy(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = make_user(username='pwpolicyadmin', role='System Administrator',
                               is_superuser=True, is_staff=True)

    def test_password_too_short_rejected(self):
        """Passwords shorter than 12 chars must be rejected."""
        otp_login(self.client, self.admin)
        resp = self.client.post(reverse('user-add'), {
            'username': 'newuser1',
            'password1': 'short',
            'password2': 'short',
            'role': 'Armorer',
        })
        # Should not redirect (form re-rendered with error)
        self.assertNotEqual(resp.status_code, 302)
