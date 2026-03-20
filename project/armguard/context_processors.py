from armguard.utils.permissions import can_add as _can_add


def nav_permissions(request):
    """
    Injects sidebar permission flags into every template context.
    Replaces the previous is_staff checks in base.html so that inventory
    '+ Add' links are shown based on UserProfile.role only.
    """
    user = request.user
    if not user.is_authenticated:
        return {'can_add_inventory': False}
    return {
        'can_add_inventory': _can_add(user),
    }
