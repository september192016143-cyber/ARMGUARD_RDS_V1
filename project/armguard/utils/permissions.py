"""
H1 FIX: Centralised permission helpers for ArmGuard RDS.

Per-module granular permissions replace the old global perm_can_add/perm_can_edit.
All checks follow this priority order:
  1. is_superuser          → always True (emergency/recovery account)
  2. role='System Administrator' → always True
  3. role='Administrator'  → read per-module flag from UserProfile
  4. role='Armorer'        → fixed access defined per helper below
  5. anything else         → False

Django built-ins:
  is_superuser — always full access (recovery only)
  is_staff     — controls Django admin panel access only; NO effect on web app
"""
from __future__ import annotations

# All Administrator sub-type role strings (including legacy 'Administrator' for backward compat)
_ADMIN_ROLES = frozenset({
    'Administrator',
    'Administrator \u2014 View Only',
    'Administrator \u2014 Edit & Add',
})


def _get_role(user) -> str:
    try:
        return user.profile.role
    except AttributeError:
        return ''


def _perm(user, flag: str, *, armorer_default: bool = False) -> bool:
    """
    Generic per-module flag reader.
    - Superuser / System Administrator → always True
    - Administrator (any sub-type) → read UserProfile.<flag>
    - Armorer → armorer_default
    - Other / no profile → False
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    role = _get_role(user)
    if role == 'System Administrator':
        return True
    if role in _ADMIN_ROLES:
        try:
            return bool(getattr(user.profile, flag))
        except AttributeError:
            return False
    if role == 'Armorer':
        # Armorer permissions are fixed per-helper (armorer_default), not
        # configurable per-user via DB flags.  Reading the DB field caused a
        # regression: new profiles always have perm_* = False (the field
        # default), which would never fall through to armorer_default=True.
        return armorer_default
    return False


# ── Inventory module ──────────────────────────────────────────────────────────
def can_view_inventory(user) -> bool:
    """May view inventory lists (pistols, rifles, ammo, magazines, accessories)."""
    return _perm(user, 'perm_inventory_view', armorer_default=True)

def can_add_inventory(user) -> bool:
    """May create new inventory records."""
    return _perm(user, 'perm_inventory_add', armorer_default=False)

def can_edit_inventory(user) -> bool:
    """May edit existing inventory records."""
    return _perm(user, 'perm_inventory_edit', armorer_default=False)

def can_delete_inventory(user) -> bool:
    """May delete inventory records."""
    return _perm(user, 'perm_inventory_delete', armorer_default=False)


# ── Personnel module ──────────────────────────────────────────────────────────
def can_view_personnel(user) -> bool:
    """May view personnel list and detail pages."""
    return _perm(user, 'perm_personnel_view', armorer_default=True)

def can_add_personnel(user) -> bool:
    """May create new personnel records."""
    return _perm(user, 'perm_personnel_add', armorer_default=False)

def can_edit_personnel(user) -> bool:
    """May edit personnel records and assign weapons."""
    return _perm(user, 'perm_personnel_edit', armorer_default=False)

def can_delete_personnel(user) -> bool:
    """May delete personnel records."""
    return _perm(user, 'perm_personnel_delete', armorer_default=False)


# ── Transactions module ───────────────────────────────────────────────────────
def can_view_transactions(user) -> bool:
    """May view transaction list and detail pages."""
    return _perm(user, 'perm_transaction_view', armorer_default=True)

def can_create_transaction(user) -> bool:
    """May create new withdrawal/return transactions."""
    return _perm(user, 'perm_transaction_create', armorer_default=True)


# ── Reports & Print module (separate flags) ───────────────────────────────────
def can_view_reports(user) -> bool:
    """May view and download analytical reports."""
    return _perm(user, 'perm_reports', armorer_default=True)

def can_print(user) -> bool:
    """May access the Print module: generate/print ID cards, item tags, and PDF transaction forms."""
    return _perm(user, 'perm_print', armorer_default=True)


# ── User management module ────────────────────────────────────────────────────
def can_manage_users(user) -> bool:
    """May view, create, edit, and delete user accounts."""
    return _perm(user, 'perm_users_manage', armorer_default=False)


# ── Convenience / backward-compat helpers ────────────────────────────────────
def is_admin(user) -> bool:
    """True for System Administrators, all Administrator sub-types, and superusers."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return _get_role(user) in (_ADMIN_ROLES | {'System Administrator'})

# Legacy aliases kept so any template tags or third-party code still resolve.
can_add    = can_add_inventory
can_edit   = can_edit_inventory
can_delete = can_delete_inventory
can_manage_inventory       = can_view_inventory
can_edit_delete_inventory  = can_edit_inventory
