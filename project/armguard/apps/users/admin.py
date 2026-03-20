from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User, Group
from .models import UserProfile, AuditLog
from armguard.apps.personnel.models import Personnel

# ── Admin site hardening ──────────────────────────────────────────────────────
# Restrict Django admin to superusers only. Armorers, Administrators, and
# System Administrators manage everything through the main ArmGuard interface;
# the Django admin is a superuser-level emergency/recovery tool only.
def _superuser_only(self, request):
    return request.user.is_active and request.user.is_superuser

admin.site.__class__.has_permission = _superuser_only

# ── Branding ──────────────────────────────────────────────────────────────────
admin.site.site_header = "ArmGuard RDS Administration"
admin.site.site_title  = "ArmGuard RDS"
admin.site.index_title = "Database Administration"

# ── Remove unused / sensitive built-in models ─────────────────────────────────
# Groups: ArmGuard uses UserProfile.role for RBAC — Django's built-in Group /
# Permission system is not used. Hiding it prevents confusion and misuse.
admin.site.unregister(Group)

# Auth Tokens: DRF tokens are issued programmatically (ThrottledObtainAuthToken).
# Exposing raw token values in the Django admin is a security risk — a superuser
# account compromise would immediately reveal all API bearer tokens.
from rest_framework.authtoken.models import Token as _AuthToken
try:
    admin.site.unregister(_AuthToken)
except admin.sites.NotRegistered:
    pass  # authtoken app may not have registered yet in some startup orders


class UserProfileInline(admin.StackedInline):
    """Shows the effective role + granular flags (driven by Group assignment)."""
    model = UserProfile
    can_delete = False
    verbose_name = "ArmGuard Role (set via Group above)"
    verbose_name_plural = "ArmGuard Role (set via Group above)"
    fields = ('role', 'perm_can_add', 'perm_can_edit')
    readonly_fields = ('role',)   # role is synced from Group — not edited directly
    extra = 1
    max_num = 1


class PersonnelInline(admin.StackedInline):
    """
    Personnel record inline — lets you create/edit the linked Personnel
    record directly from the User add/change page.
    Personnel.user is a OneToOneField(AUTH_USER_MODEL) so at most one record appears.
    """
    model = Personnel
    fk_name = 'user'
    can_delete = False
    verbose_name = "Personnel Record"
    verbose_name_plural = "Personnel Record"
    extra = 1
    max_num = 1
    fields = (
        'rank',
        'first_name',
        'middle_initial',
        'last_name',
        'AFSN',
        'group',
        'squadron',
        'status',
        'personnel_image',
    )

    def save_new(self, form, commit=True):
        """Set created_by/updated_by from request when saving a new Personnel via inline."""
        obj = super().save_new(form, commit=False)
        request = self._request  # set by PersonnelInlineMixin below
        if request:
            obj.created_by = request.user.username
            obj.updated_by = request.user.username
        if commit:
            obj.save()
        return obj


class CustomUserAdmin(BaseUserAdmin):
    """
    Extends the default UserAdmin to include:
      - ArmGuard Role Group assignment at the top
      - UserProfile inline showing effective role + permission flags
      - Personnel Record inline
      - Role column in the list view
    """
    inlines = [UserProfileInline, PersonnelInline]

    # ── List view ─────────────────────────────────────────────────────────────
    list_display = ('username', 'email', 'get_full_name', 'get_role', 'is_active', 'last_login')
    list_filter   = ('is_superuser', 'is_active', 'profile__role')

    # ── Change form fieldsets ─────────────────────────────────────────────────
    # Puts the Group (role) assignment first; hides the unused Django permission
    # widget (user_permissions) since ArmGuard uses UserProfile.role instead.
    fieldsets = (
        (None, {
            'fields': ('username', 'password'),
        }),
        ('Personal info', {
            'fields': ('first_name', 'last_name', 'email'),
        }),
        ('ArmGuard Role', {
            'description': (
                'Assign the user to exactly one role Group below. '
                'The ArmGuard Role inline will update automatically on save. '
                '<br><strong>Armorer</strong> — view transactions, view inventory '
                '<br><strong>Administrator — View Only</strong> — view all records '
                '<br><strong>Administrator — Edit &amp; Add</strong> — create and edit records '
                '<br><strong>Superuser status</strong> — full system access (recovery only)'
            ),
            'fields': ('groups', 'is_superuser'),
        }),
        ('Account status', {
            'fields': ('is_active', 'is_staff'),
        }),
        ('Important dates', {
            'fields': ('last_login', 'date_joined'),
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2'),
        }),
        ('ArmGuard Role', {
            'fields': ('groups', 'is_superuser'),
        }),
        ('Personal info', {
            'fields': ('first_name', 'last_name', 'email'),
        }),
    )

    @admin.display(description='Role', ordering='profile__role')
    def get_role(self, obj):
        if obj.is_superuser:
            return '★ Superuser'
        try:
            return obj.profile.role or '—'
        except Exception:
            return '—'

    def save_formset(self, request, form, formset, change):
        """Pass request into personnel formset so created_by/updated_by are captured."""
        instances = formset.save(commit=False)
        for obj in instances:
            if isinstance(obj, Personnel):
                if not obj.pk:
                    obj.created_by = request.user.username
                obj.updated_by = request.user.username
                obj.user = form.instance   # link to the just-saved User
                obj.save()
        formset.save_m2m()

    def get_inline_instances(self, request, obj=None):
        return [inline(self.model, self.admin_site) for inline in [UserProfileInline, PersonnelInline]]


# Replace the default User admin with our custom one
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only audit log viewer. No records may be added, changed, or deleted via admin."""
    list_display = ('timestamp', 'user', 'action', 'model_name', 'object_pk', 'ip_address')
    list_filter = ('action', 'model_name')
    search_fields = ('user__username', 'model_name', 'object_pk', 'message', 'ip_address')
    date_hierarchy = 'timestamp'
    readonly_fields = ('timestamp', 'user', 'action', 'model_name', 'object_pk', 'message', 'ip_address')
    ordering = ('-timestamp',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
