from armguard.utils.permissions import (
    can_view_inventory, can_add_inventory, can_edit_inventory, can_delete_inventory,
    can_view_personnel, can_add_personnel, can_edit_personnel, can_delete_personnel,
    can_view_transactions, can_create_transaction,
    can_view_reports, can_print,
    can_manage_users,
)
from armguard.apps.camera.permissions import has_camera_role


def nav_permissions(request):
    """
    Injects per-module permission flags and site settings into every template context.
    Templates use these to show/hide sidebar links and action buttons.
    """
    from armguard.apps.users.models import SystemSettings
    user = request.user
    if not user.is_authenticated:
        return {
            'can_add_inventory': False,
            'can_view_inventory': False,
            'can_edit_inventory': False,
            'can_delete_inventory': False,
            'can_view_personnel': False,
            'can_add_personnel': False,
            'can_edit_personnel': False,
            'can_delete_personnel': False,
            'can_view_transactions': False,
            'can_create_transaction': False,
            'can_view_reports': False,
            'can_print': False,
            'can_manage_users': False,
            'can_use_camera': False,
            'site_settings': SystemSettings.get(),
        }
    return {
        'can_view_inventory':    can_view_inventory(user),
        'can_add_inventory':     can_add_inventory(user),
        'can_edit_inventory':    can_edit_inventory(user),
        'can_delete_inventory':  can_delete_inventory(user),
        'can_view_personnel':    can_view_personnel(user),
        'can_add_personnel':     can_add_personnel(user),
        'can_edit_personnel':    can_edit_personnel(user),
        'can_delete_personnel':  can_delete_personnel(user),
        'can_view_transactions': can_view_transactions(user),
        'can_create_transaction': can_create_transaction(user),
        'can_view_reports':      can_view_reports(user),
        'can_print':             can_print(user),
        'can_manage_users':      can_manage_users(user),
        'can_use_camera':        has_camera_role(user),
        'site_settings':         SystemSettings.get(),
    }


def session_settings(request):
    """Inject the per-role idle timeout for the current user into every template context."""
    from armguard.apps.users.models import SystemSettings
    user = request.user
    if not user.is_authenticated:
        return {'IDLE_SESSION_TIMEOUT': 0}
    s = SystemSettings.get()
    if user.is_superuser:
        timeout = s.timeout_superuser
    else:
        role = getattr(getattr(user, 'profile', None), 'role', '')
        _map = {
            'System Administrator':      s.timeout_system_admin,
            'Administrator — View Only': s.timeout_admin_view_only,
            'Administrator — Edit & Add': s.timeout_admin_edit_add,
            'Armorer':                   s.timeout_armorer,
        }
        timeout = _map.get(role, 1800)
    return {'IDLE_SESSION_TIMEOUT': timeout}
