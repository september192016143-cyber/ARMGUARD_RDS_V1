"""
H4 FIX: Test coverage for the print app.

Covers:
  - serve_item_tag_image: path traversal prevention, 404 on unknown DB item
  - print_item_tags: authentication guard

Run with:
    python manage.py test armguard.apps.print
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from armguard.apps.inventory.models import Pistol

User = get_user_model()


def _login_with_otp(client, user):
    """Log the user in and mark the session as OTP-verified."""
    client.force_login(user)
    session = client.session
    session['_otp_step_done'] = True
    session.save()


class TestServeItemTagImage(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='printuser', password='TestPass123!')
        # Create a pistol so the DB check passes (the file itself won't exist,
        # so we expect a 404 on the file-not-found branch, not on the DB branch).
        self.pistol = Pistol(model='M1911', serial_number='SN-P-PRINT-001',
                             item_status='Available', item_condition='Serviceable')
        self.pistol.save()

    def test_unauthenticated_redirects(self):
        item_id = self.pistol.item_id
        resp = self.client.get(
            reverse('print_handler:serve_item_tag_image', kwargs={'item_id': item_id})
        )
        self.assertIn(resp.status_code, (301, 302))

    def test_unknown_item_returns_404(self):
        _login_with_otp(self.client, self.user)
        resp = self.client.get(
            reverse('print_handler:serve_item_tag_image', kwargs={'item_id': 'NONEXISTENT-9999'})
        )
        self.assertEqual(resp.status_code, 404)

    def test_path_traversal_returns_404(self):
        """A traversal sequence in the item_id must return 404, not serve arbitrary files."""
        _login_with_otp(self.client, self.user)
        # The URL router will percent-encode slashes, but double-dots alone are checked.
        resp = self.client.get(
            reverse('print_handler:serve_item_tag_image', kwargs={'item_id': '..%2F..%2Fetc%2Fpasswd'})
        )
        self.assertEqual(resp.status_code, 404)


class TestPrintItemTagsView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='printview', password='TestPass123!')

    def test_anonymous_redirects(self):
        resp = self.client.get(reverse('print_handler:print_item_tags'))
        self.assertIn(resp.status_code, (301, 302))

    def test_authenticated_returns_200(self):
        _login_with_otp(self.client, self.user)
        resp = self.client.get(reverse('print_handler:print_item_tags'))
        self.assertEqual(resp.status_code, 200)
