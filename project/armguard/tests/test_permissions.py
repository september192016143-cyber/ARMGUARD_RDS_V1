"""
Unit tests for armguard/utils/permissions.py.
Verifies every helper function returns the correct True/False for each role,
for anonymous users, and for the Django built-in superuser/staff flags.
"""
from django.test import TestCase
from unittest.mock import MagicMock
from armguard.utils.permissions import (
    is_admin,
    can_manage_inventory,
    can_edit_delete_inventory,
    can_create_transaction,
    can_delete,
    can_add,
)
from armguard.tests.factories import make_user


def _anon():
    """Return a mock object that behaves like an unauthenticated AnonymousUser."""
    user = MagicMock()
    user.is_authenticated = False
    return user


class TestIsAdmin(TestCase):
    def test_anonymous_is_false(self):
        self.assertFalse(is_admin(_anon()))

    def test_superuser_is_true(self):
        u = make_user(username='perm_su', is_superuser=True)
        self.assertTrue(is_admin(u))

    def test_staff_is_true(self):
        u = make_user(username='perm_staff', is_staff=True)
        self.assertTrue(is_admin(u))

    def test_system_administrator_role_is_true(self):
        u = make_user(username='perm_sysadm', role='System Administrator')
        self.assertTrue(is_admin(u))

    def test_administrator_role_is_true(self):
        u = make_user(username='perm_adm', role='Administrator')
        self.assertTrue(is_admin(u))

    def test_armorer_role_is_false(self):
        u = make_user(username='perm_arm', role='Armorer')
        self.assertFalse(is_admin(u))


class TestCanManageInventory(TestCase):
    def test_anonymous_is_false(self):
        self.assertFalse(can_manage_inventory(_anon()))

    def test_armorer_is_true(self):
        u = make_user(username='cmi_arm', role='Armorer')
        self.assertTrue(can_manage_inventory(u))

    def test_administrator_is_true(self):
        u = make_user(username='cmi_adm', role='Administrator')
        self.assertTrue(can_manage_inventory(u))

    def test_system_administrator_is_true(self):
        u = make_user(username='cmi_sa', role='System Administrator')
        self.assertTrue(can_manage_inventory(u))

    def test_superuser_is_true(self):
        u = make_user(username='cmi_su', is_superuser=True)
        self.assertTrue(can_manage_inventory(u))


class TestCanEditDeleteInventory(TestCase):
    def test_anonymous_is_false(self):
        self.assertFalse(can_edit_delete_inventory(_anon()))

    def test_armorer_is_false(self):
        u = make_user(username='cedi_arm', role='Armorer')
        self.assertFalse(can_edit_delete_inventory(u))

    def test_administrator_is_true(self):
        u = make_user(username='cedi_adm', role='Administrator')
        self.assertTrue(can_edit_delete_inventory(u))

    def test_system_administrator_is_true(self):
        u = make_user(username='cedi_sa', role='System Administrator')
        self.assertTrue(can_edit_delete_inventory(u))

    def test_superuser_is_true(self):
        u = make_user(username='cedi_su', is_superuser=True)
        self.assertTrue(can_edit_delete_inventory(u))


class TestCanCreateTransaction(TestCase):
    def test_anonymous_is_false(self):
        self.assertFalse(can_create_transaction(_anon()))

    def test_armorer_is_true(self):
        u = make_user(username='cct_arm', role='Armorer')
        self.assertTrue(can_create_transaction(u))

    def test_administrator_is_true(self):
        u = make_user(username='cct_adm', role='Administrator')
        self.assertTrue(can_create_transaction(u))

    def test_system_administrator_is_true(self):
        u = make_user(username='cct_sa', role='System Administrator')
        self.assertTrue(can_create_transaction(u))

    def test_superuser_is_true(self):
        u = make_user(username='cct_su', is_superuser=True)
        self.assertTrue(can_create_transaction(u))


class TestCanDelete(TestCase):
    def test_anonymous_is_false(self):
        self.assertFalse(can_delete(_anon()))

    def test_armorer_is_false(self):
        u = make_user(username='cd_arm', role='Armorer')
        self.assertFalse(can_delete(u))

    def test_administrator_role_is_false(self):
        """Administrators may add/edit but NOT delete — only System Admins can."""
        u = make_user(username='cd_adm', role='Administrator')
        self.assertFalse(can_delete(u))

    def test_system_administrator_is_true(self):
        u = make_user(username='cd_sa', role='System Administrator')
        self.assertTrue(can_delete(u))

    def test_superuser_is_true(self):
        u = make_user(username='cd_su', is_superuser=True)
        self.assertTrue(can_delete(u))


class TestCanAdd(TestCase):
    def test_anonymous_is_false(self):
        self.assertFalse(can_add(_anon()))

    def test_armorer_is_false(self):
        u = make_user(username='ca_arm', role='Armorer')
        self.assertFalse(can_add(u))

    def test_system_administrator_is_true(self):
        u = make_user(username='ca_sa', role='System Administrator')
        self.assertTrue(can_add(u))

    def test_superuser_is_true(self):
        u = make_user(username='ca_su', is_superuser=True)
        self.assertTrue(can_add(u))
