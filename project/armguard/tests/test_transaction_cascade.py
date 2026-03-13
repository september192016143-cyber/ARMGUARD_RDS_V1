"""
Cascade / business-logic tests for the Transaction model.

These tests verify the side-effects of Transaction.save():
  • Withdrawal → Pistol/Rifle.item_status becomes 'Issued'
  • Withdrawal → Personnel.pistol_item_issued / rifle_item_issued is set
  • Withdrawal → TransactionLogs record created with status='Open'
  • Return → Pistol/Rifle.item_status becomes 'Available'
  • Return → Personnel clears pistol_item_issued / rifle_item_issued
  • Return → TransactionLogs record closed (status='Closed')
  • Validation → duplicate pistol withdrawal raises ValidationError
  • Validation → return without open log raises ValidationError

All tests use the shared factory helpers and rely on the QR-mock fixture
so no actual files are written to disk.
"""
import threading
from django.test import TestCase, TransactionTestCase
from django.core.exceptions import ValidationError

from armguard.apps.transactions.models import Transaction, TransactionLogs
from armguard.tests.factories import (
    make_user, make_personnel, make_pistol, make_rifle, otp_login,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _withdrawal(personnel, pistol=None, rifle=None, user=None):
    """Create a Withdrawal transaction via Transaction.save()."""
    txn = Transaction(
        transaction_type='Withdrawal',
        issuance_type='TR (Temporary Receipt)',
        personnel=personnel,
        pistol=pistol,
        rifle=rifle,
        purpose='Duty Sentinel',
        transaction_personnel=(user.username if user else 'test_user'),
    )
    txn.save()
    return txn


def _return(personnel, pistol=None, rifle=None, user=None):
    """Create a Return transaction via Transaction.save()."""
    txn = Transaction(
        transaction_type='Return',
        personnel=personnel,
        pistol=pistol,
        rifle=rifle,
        purpose='Duty Sentinel',
        transaction_personnel=(user.username if user else 'test_user'),
    )
    txn.save()
    return txn


# ---------------------------------------------------------------------------
# Pistol cascade tests
# ---------------------------------------------------------------------------

class TestPistolWithdrawalCascade(TestCase):
    """Verify all side-effects of a pistol Withdrawal."""

    def setUp(self):
        self.personnel = make_personnel(afsn='CASC-P-001')
        self.pistol = make_pistol(serial='CASC-PISTOL-001')
        self.user = make_user(username='casc_p_user', role='Armorer')

    def test_pistol_status_becomes_issued(self):
        _withdrawal(self.personnel, pistol=self.pistol, user=self.user)
        self.pistol.refresh_from_db()
        self.assertEqual(self.pistol.item_status, 'Issued')

    def test_personnel_pistol_item_issued_set(self):
        _withdrawal(self.personnel, pistol=self.pistol, user=self.user)
        self.personnel.refresh_from_db()
        self.assertIsNotNone(self.personnel.pistol_item_issued)

    def test_transaction_log_created_open(self):
        txn = _withdrawal(self.personnel, pistol=self.pistol, user=self.user)
        logs = TransactionLogs.objects.filter(personnel_id=self.personnel)
        self.assertEqual(logs.count(), 1)
        log = logs.first()
        self.assertEqual(log.log_status, 'Open')
        self.assertEqual(log.withdraw_pistol, self.pistol)


class TestPistolReturnCascade(TestCase):
    """Verify all side-effects of a pistol Return."""

    def setUp(self):
        self.personnel = make_personnel(afsn='CASC-P-002')
        self.pistol = make_pistol(serial='CASC-PISTOL-002')
        self.user = make_user(username='casc_p_user2', role='Armorer')
        # Issue first so we can return
        _withdrawal(self.personnel, pistol=self.pistol, user=self.user)
        self.pistol.refresh_from_db()
        self.personnel.refresh_from_db()

    def test_pistol_status_becomes_available_after_return(self):
        _return(self.personnel, pistol=self.pistol, user=self.user)
        self.pistol.refresh_from_db()
        self.assertEqual(self.pistol.item_status, 'Available')

    def test_personnel_pistol_item_issued_cleared_after_return(self):
        _return(self.personnel, pistol=self.pistol, user=self.user)
        self.personnel.refresh_from_db()
        self.assertIsNone(self.personnel.pistol_item_issued)

    def test_transaction_log_closed_after_return(self):
        _return(self.personnel, pistol=self.pistol, user=self.user)
        log = TransactionLogs.objects.filter(personnel_id=self.personnel).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.log_status, 'Closed')
        self.assertIsNotNone(log.return_pistol)


# ---------------------------------------------------------------------------
# Rifle cascade tests
# ---------------------------------------------------------------------------

class TestRifleWithdrawalCascade(TestCase):
    """Verify all side-effects of a rifle Withdrawal."""

    def setUp(self):
        self.personnel = make_personnel(afsn='CASC-R-001')
        self.rifle = make_rifle(serial='CASC-RIFLE-001')
        self.user = make_user(username='casc_r_user', role='Armorer')

    def test_rifle_status_becomes_issued(self):
        _withdrawal(self.personnel, rifle=self.rifle, user=self.user)
        self.rifle.refresh_from_db()
        self.assertEqual(self.rifle.item_status, 'Issued')

    def test_personnel_rifle_item_issued_set(self):
        _withdrawal(self.personnel, rifle=self.rifle, user=self.user)
        self.personnel.refresh_from_db()
        self.assertIsNotNone(self.personnel.rifle_item_issued)

    def test_transaction_log_created_for_rifle(self):
        _withdrawal(self.personnel, rifle=self.rifle, user=self.user)
        logs = TransactionLogs.objects.filter(personnel_id=self.personnel)
        self.assertEqual(logs.count(), 1)


class TestRifleReturnCascade(TestCase):
    """Verify all side-effects of a rifle Return."""

    def setUp(self):
        self.personnel = make_personnel(afsn='CASC-R-002')
        self.rifle = make_rifle(serial='CASC-RIFLE-002')
        self.user = make_user(username='casc_r_user2', role='Armorer')
        _withdrawal(self.personnel, rifle=self.rifle, user=self.user)
        self.rifle.refresh_from_db()
        self.personnel.refresh_from_db()

    def test_rifle_status_becomes_available_after_return(self):
        _return(self.personnel, rifle=self.rifle, user=self.user)
        self.rifle.refresh_from_db()
        self.assertEqual(self.rifle.item_status, 'Available')

    def test_personnel_rifle_cleared_after_return(self):
        _return(self.personnel, rifle=self.rifle, user=self.user)
        self.personnel.refresh_from_db()
        self.assertIsNone(self.personnel.rifle_item_issued)


# ---------------------------------------------------------------------------
# Business-rule validation tests
# ---------------------------------------------------------------------------

class TestDuplicatePistolValidation(TestCase):
    """Cannot issue a second pistol to the same personnel."""

    def setUp(self):
        self.personnel = make_personnel(afsn='CASC-DUP-001')
        self.pistol1 = make_pistol(serial='CASC-DUP-P-001')
        self.pistol2 = make_pistol(serial='CASC-DUP-P-002')
        self.user = make_user(username='casc_dup_user', role='Armorer')
        _withdrawal(self.personnel, pistol=self.pistol1, user=self.user)
        self.personnel.refresh_from_db()

    def test_second_pistol_raises_validation_error(self):
        txn = Transaction(
            transaction_type='Withdrawal',
            issuance_type='TR (Temporary Receipt)',
            personnel=self.personnel,
            pistol=self.pistol2,
            purpose='Duty Sentinel',
        )
        with self.assertRaises(ValidationError):
            txn.clean()

    def test_second_pistol_cannot_save(self):
        with self.assertRaises((ValidationError, Exception)):
            _withdrawal(self.personnel, pistol=self.pistol2, user=self.user)


class TestReturnWithoutWithdrawalValidation(TestCase):
    """Cannot return a pistol that was never issued to this personnel."""

    def setUp(self):
        self.personnel = make_personnel(afsn='CASC-RET-001')
        self.pistol = make_pistol(serial='CASC-RET-P-001')
        # Keep pistol Available — no open log exists

    def test_return_without_open_log_raises(self):
        txn = Transaction(
            transaction_type='Return',
            personnel=self.personnel,
            pistol=self.pistol,
            purpose='Duty Sentinel',
        )
        with self.assertRaises(ValidationError):
            txn.clean()


class TestUnavailablePistolValidation(TestCase):
    """Cannot withdraw a pistol that is already Issued to someone else."""

    def setUp(self):
        self.personnel1 = make_personnel(afsn='CASC-UAV-001')
        self.personnel2 = make_personnel(afsn='CASC-UAV-002')
        self.pistol = make_pistol(serial='CASC-UAV-P-001')
        self.user = make_user(username='casc_uav_user', role='Armorer')
        # Issue to personnel1
        _withdrawal(self.personnel1, pistol=self.pistol, user=self.user)
        self.pistol.refresh_from_db()

    def test_already_issued_pistol_cannot_be_withdrawn(self):
        txn = Transaction(
            transaction_type='Withdrawal',
            issuance_type='TR (Temporary Receipt)',
            personnel=self.personnel2,
            pistol=self.pistol,
            purpose='Duty Sentinel',
        )
        with self.assertRaises(ValidationError):
            txn.clean()


# ---------------------------------------------------------------------------
# Concurrency test (requires TransactionTestCase for real DB isolation)
# ---------------------------------------------------------------------------

class TestConcurrentPistolWithdrawal(TransactionTestCase):
    """
    Two simultaneous requests to issue the same pistol: only one should succeed.
    Uses threads + TransactionTestCase (real DB transactions, not wrapped in a
    test transaction) so select_for_update() locking is exercised properly.
    """

    def setUp(self):
        self.personnel1 = make_personnel(afsn='CONC-001')
        self.personnel2 = make_personnel(afsn='CONC-002')
        self.pistol = make_pistol(serial='CONC-PISTOL-001')

    def test_only_one_thread_can_issue_the_same_pistol(self):
        results = []
        errors = []

        def attempt_withdrawal(personnel):
            try:
                _withdrawal(personnel, pistol=self.pistol)
                results.append('success')
            except Exception as exc:
                errors.append(str(exc))

        t1 = threading.Thread(target=attempt_withdrawal, args=(self.personnel1,))
        t2 = threading.Thread(target=attempt_withdrawal, args=(self.personnel2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly one should succeed; one should fail with a ValidationError or DB error
        self.assertEqual(len(results) + len(errors), 2)
        self.assertEqual(len(results), 1, f'Expected 1 success, got: {results}; errors: {errors}')

        self.pistol.refresh_from_db()
        self.assertEqual(self.pistol.item_status, 'Issued')
