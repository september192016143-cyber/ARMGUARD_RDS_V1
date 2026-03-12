"""
H1 FIX: Centralised permission helpers for ArmGuard RDS.

Previously each app defined its own copy of the same role-check function,
creating divergence risk (a change in one copy not propagated to others).
All view modules now import from here.

Roles (from UserProfile.role):
  System Administrator — full admin access (same as is_staff/is_superuser)
  Administrator        — full access (create/edit/delete all records)
  Armorer              — create and view transactions; view inventory and personnel

Django built-ins override are also respected:
  is_superuser          — always admin (full access)
  is_staff              — admin-level access (Django admin panel)
"""


def _get_role(user) -> str:
    """Return the UserProfile role string, or '' if the profile is absent."""
    try:
        return user.profile.role
    except AttributeError:
        return ''


def is_admin(user) -> bool:
    """True for System Administrators, Administrators, superusers, and staff."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return _get_role(user) in ('System Administrator', 'Administrator')


def can_manage_inventory(user) -> bool:
    """True for Armorers, Administrators, System Administrators, superusers, staff."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return _get_role(user) in ('System Administrator', 'Administrator', 'Armorer')


def can_edit_delete_inventory(user) -> bool:
    """System Administrators, Administrators, and superusers may edit inventory.
    Use can_delete() to check delete permission — Administrators cannot delete."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return _get_role(user) in ('System Administrator', 'Administrator')


def can_create_transaction(user) -> bool:
    """Superusers, staff, and named management/armorer roles may create transactions."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return _get_role(user) in ('System Administrator', 'Administrator', 'Armorer')


def can_delete(user) -> bool:
    """Only superusers and System Administrators may delete records.
    Administrators (role='Administrator') are restricted to add/edit only."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return _get_role(user) == 'System Administrator'


def can_add(user) -> bool:
    """True if the user may create new records.

    - Superuser / System Administrator: always True.
    - Administrator: True only when UserProfile.perm_can_add is checked.
    - Armorer and others: False (transactions only, no CRUD on records).
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    role = _get_role(user)
    if role == 'System Administrator':
        return True
    if role == 'Administrator':
        try:
            return bool(user.profile.perm_can_add)
        except AttributeError:
            return True
    return False


def can_edit(user) -> bool:
    """True if the user may edit / update existing records.

    - Superuser / System Administrator: always True.
    - Administrator: True only when UserProfile.perm_can_edit is checked.
    - Armorer and others: False.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    role = _get_role(user)
    if role == 'System Administrator':
        return True
    if role == 'Administrator':
        try:
            return bool(user.profile.perm_can_edit)
        except AttributeError:
            return True
    return False
