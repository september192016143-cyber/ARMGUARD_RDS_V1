"""
Tests for the dashboard view.
Verifies authentication, context keys, caching behaviour, and cache invalidation.
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.core.cache import cache
from django.utils import timezone
from armguard.tests.factories import make_user, otp_login


class TestDashboardView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user(username='dash_user', role='Armorer')
        cache.clear()  # Start each test with a clean cache

    def test_requires_login(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertIn(resp.status_code, (301, 302))

    def test_authenticated_user_gets_200(self):
        otp_login(self.client, self.user)
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'dashboard/dashboard.html')

    # ── Context sanity checks ─────────────────────────────────────────────────

    def test_context_has_stats_keys(self):
        otp_login(self.client, self.user)
        resp = self.client.get(reverse('dashboard'))
        ctx = resp.context
        expected_keys = [
            'total_personnel', 'total_pistols', 'total_rifles',
            'total_transactions', 'withdrawals_today', 'returns_today',
        ]
        for key in expected_keys:
            self.assertIn(key, ctx, f"Missing context key: {key}")

    def test_context_has_inventory_table_keys(self):
        otp_login(self.client, self.user)
        resp = self.client.get(reverse('dashboard'))
        ctx = resp.context
        table_keys = [
            'inventory_rows', 'inventory_totals',
            'ammo_rows', 'ammo_totals',
            'magazine_rows', 'magazine_totals',
            'accessory_rows', 'accessory_totals',
        ]
        for key in table_keys:
            self.assertIn(key, ctx, f"Missing context key: {key}")

    # ── Cache behaviour ───────────────────────────────────────────────────────

    def test_stats_cache_is_populated_after_first_request(self):
        otp_login(self.client, self.user)
        today = timezone.localdate()
        stats_key = f'dashboard_stats_{today}'

        # Cache should be empty before the request
        self.assertIsNone(cache.get(stats_key))

        self.client.get(reverse('dashboard'))

        # Cache must be populated now
        self.assertIsNotNone(cache.get(stats_key))

    def test_inventory_tables_cache_is_populated_after_first_request(self):
        otp_login(self.client, self.user)
        tables_key = 'dashboard_inventory_tables'

        self.assertIsNone(cache.get(tables_key))

        self.client.get(reverse('dashboard'))

        self.assertIsNotNone(cache.get(tables_key))

    def test_second_request_hits_cache(self):
        """The stats and tables cache keys should already be populated on the second call,
        and the response must still succeed (no errors due to cached data)."""
        otp_login(self.client, self.user)

        self.client.get(reverse('dashboard'))   # populates cache
        resp = self.client.get(reverse('dashboard'))  # should hit cache

        self.assertEqual(resp.status_code, 200)

    def test_cache_invalidation_clears_stats(self):
        """Simulate what create_transaction() does: delete cache keys and verify they're gone."""
        today = timezone.localdate()
        stats_key = f'dashboard_stats_{today}'
        tables_key = 'dashboard_inventory_tables'

        otp_login(self.client, self.user)
        self.client.get(reverse('dashboard'))  # populate cache

        self.assertIsNotNone(cache.get(stats_key))
        self.assertIsNotNone(cache.get(tables_key))

        # Simulate transaction-creation cache invalidation
        cache.delete(stats_key)
        cache.delete(tables_key)

        self.assertIsNone(cache.get(stats_key))
        self.assertIsNone(cache.get(tables_key))

        # Dashboard must re-query and re-populate correctly
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(cache.get(stats_key))
        self.assertIsNotNone(cache.get(tables_key))
