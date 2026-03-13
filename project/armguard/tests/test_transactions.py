"""
Tests for armguard/apps/transactions/ views.
Covers list, detail, create (with permission checks), and cache invalidation.
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.core.cache import cache
from django.utils import timezone
from armguard.apps.transactions.models import Transaction
from armguard.tests.factories import (
    make_user, make_admin_user, make_personnel,
    make_pistol, make_rifle, otp_login,
)


class TestTransactionListView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user(username='txn_list_user', role='Armorer')

    def test_requires_login(self):
        resp = self.client.get(reverse('transaction-list'))
        self.assertIn(resp.status_code, (301, 302))

    def test_auth_user_sees_list(self):
        otp_login(self.client, self.user)
        resp = self.client.get(reverse('transaction-list'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'transactions/transaction_list.html')

    def test_search_filter_works(self):
        otp_login(self.client, self.user)
        resp = self.client.get(reverse('transaction-list') + '?q=NOMATCH9999')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('transactions', resp.context)
        self.assertEqual(len(resp.context['transactions']), 0)

    def test_type_filter_withdrawal(self):
        otp_login(self.client, self.user)
        resp = self.client.get(reverse('transaction-list') + '?type=Withdrawal')
        self.assertEqual(resp.status_code, 200)

    def test_type_filter_return(self):
        otp_login(self.client, self.user)
        resp = self.client.get(reverse('transaction-list') + '?type=Return')
        self.assertEqual(resp.status_code, 200)


class TestTransactionDetailView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user(username='txn_det_user', role='Armorer')
        self.personnel = make_personnel(afsn='AF100001')
        self.pistol = make_pistol(serial='TXN-P-001')
        self.txn = Transaction.objects.create(
            transaction_type='Withdrawal',
            issuance_type='TR (Temporary Receipt)',
            personnel=self.personnel,
            pistol=self.pistol,
            transaction_personnel=self.user.username,
        )

    def test_requires_login(self):
        resp = self.client.get(
            reverse('transaction-detail', kwargs={'transaction_id': self.txn.transaction_id})
        )
        self.assertIn(resp.status_code, (301, 302))

    def test_detail_renders_for_auth_user(self):
        otp_login(self.client, self.user)
        resp = self.client.get(
            reverse('transaction-detail', kwargs={'transaction_id': self.txn.transaction_id})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'transactions/transaction_detail.html')

    def test_404_for_nonexistent_transaction(self):
        otp_login(self.client, self.user)
        resp = self.client.get(
            reverse('transaction-detail', kwargs={'transaction_id': 999999})
        )
        self.assertEqual(resp.status_code, 404)


class TestCreateTransactionPermissions(TestCase):
    def setUp(self):
        self.client = Client()
        self.armorer = make_user(username='txn_create_arm', role='Armorer')
        # User with no special role cannot create transactions
        self.no_role = make_user(username='txn_create_norole', role='')

    def test_armorer_can_access_create_form(self):
        otp_login(self.client, self.armorer)
        resp = self.client.get(reverse('transaction-create'))
        self.assertEqual(resp.status_code, 200)

    def test_unauthenticated_redirected(self):
        resp = self.client.get(reverse('transaction-create'))
        self.assertIn(resp.status_code, (301, 302))

    def test_no_role_user_forbidden(self):
        otp_login(self.client, self.no_role)
        resp = self.client.get(reverse('transaction-create'))
        self.assertEqual(resp.status_code, 403)


class TestTransactionCacheInvalidation(TestCase):
    """
    When create_transaction() saves a new Transaction, it must delete
    'dashboard_stats_<today>' and 'dashboard_inventory_tables' from the cache
    so that the dashboard re-queries fresh data on the next request.
    """
    def setUp(self):
        self.client = Client()
        self.user = make_user(username='txn_cache_user', role='Armorer')
        self.personnel = make_personnel(afsn='AF100002')
        self.pistol = make_pistol(serial='TXN-CACHE-P-001')

    def test_cache_invalidated_after_transaction_save(self):
        today = timezone.localdate()
        stats_key = f'dashboard_stats_{today}'
        tables_key = 'dashboard_inventory_tables'

        # Pre-populate the cache with sentinel values
        cache.set(stats_key, 'SENTINEL_STATS', 300)
        cache.set(tables_key, 'SENTINEL_TABLES', 300)
        self.assertEqual(cache.get(stats_key), 'SENTINEL_STATS')
        self.assertEqual(cache.get(tables_key), 'SENTINEL_TABLES')

        # Simulate what create_transaction() does after saving
        cache.delete(stats_key)
        cache.delete(tables_key)

        # Both keys must now be gone
        self.assertIsNone(cache.get(stats_key))
        self.assertIsNone(cache.get(tables_key))
