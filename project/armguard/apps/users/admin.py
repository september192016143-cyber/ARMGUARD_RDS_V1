from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User, Group, Permission
from django.utils.html import format_html
from .models import UserProfile, AuditLog, ActivityLog, _sync_profile_from_groups
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
    """
    Shows the effective role (readonly — driven by Group) and the granular
    permission flags (editable — fine-tune per user after group is assigned).
    """
    model = UserProfile
    can_delete = False
    verbose_name = "ArmGuard Permissions"
    verbose_name_plural = "ArmGuard Permissions"
    fields = (
        'role',
        'perm_inventory_view', 'perm_inventory_add', 'perm_inventory_edit', 'perm_inventory_delete',
        'perm_personnel_view', 'perm_personnel_add', 'perm_personnel_edit', 'perm_personnel_delete',
        'perm_transaction_view', 'perm_transaction_create',
        'perm_reports', 'perm_print', 'perm_users_manage',
    )
    readonly_fields = ('role',)   # role is always driven by Group
    extra = 0
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
            'fields': ('is_active',),
        }),
        ('User permissions', {
            'classes': ('collapse',),
            'fields': ('user_permissions',),
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
        try:
            return obj.profile.role or '—'
        except Exception:
            return '★ Superuser' if obj.is_superuser else '—'

    def save_related(self, request, form, formsets, change):
        """
        Save M2M + all inlines, then re-sync the UserProfile if groups changed.

        Ordering problem without this override:
          1. form.save_m2m() fires m2m_changed signal → profile synced correctly
          2. UserProfileInline saves → stale form values overwrite the sync

        With this override:
          After everything saves, if the group set changed we call
          _sync_profile_from_groups() one final time so the group always wins
          for 'role' + default perm flags. When groups did NOT change, the
          admin's manually-edited perm flags are preserved as-is.
        """
        old_groups = (
            set(form.instance.groups.values_list('name', flat=True))
            if change else set()
        )
        super().save_related(request, form, formsets, change)

        user = form.instance

        # If is_superuser is set, ArmGuard groups are irrelevant and contradictory.
        # Auto-remove them so the DB state is clean and unambiguous.
        if user.is_superuser:
            armguard_groups = user.groups.filter(name__in=[
                'Armorer',
                'Administrator \u2014 View Only',
                'Administrator \u2014 Edit & Add',
            ])
            if armguard_groups.exists():
                user.groups.remove(*armguard_groups)
                self.message_user(
                    request,
                    "ArmGuard role group removed automatically — superuser status "
                    "already grants full System Administrator access.",
                    level='warning',
                )

            # Grant all Django permissions so the user_permissions widget
            # visually reflects the full access that is_superuser implies.
            all_perms = Permission.objects.all()
            if user.user_permissions.count() != all_perms.count():
                user.user_permissions.set(all_perms)

        new_groups = set(user.groups.values_list('name', flat=True))
        if old_groups != new_groups:
            _sync_profile_from_groups(user)

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
    """Read-only audit log — CRUD and auth events on key models."""

    # ── Colours for action badges ──────────────────────────────────────────
    _ACTION_COLOURS = {
        'CREATE':       '#28a745',
        'UPDATE':       '#ffc107',
        'DELETE':       '#dc3545',
        'LOGIN':        '#17a2b8',
        'LOGOUT':       '#6c757d',
        'LOGIN_FAILED': '#a71d2a',   # dark red — credential brute-force
        'OTP_FAILED':   '#c0392b',   # red — 2FA bypass attempt
        'OTHER':        '#6f42c1',
    }

    list_display  = ('timestamp', 'user', 'action_badge', 'model_name', 'object_pk',
                     'short_message', 'ip_address', 'integrity_ok')
    list_filter   = ('action', 'model_name')
    search_fields = ('user__username', 'model_name', 'object_pk', 'message', 'ip_address')
    date_hierarchy = 'timestamp'
    ordering       = ('-timestamp',)
    list_per_page  = 50


    readonly_fields = (
        'timestamp', 'user', 'action', 'model_name', 'object_pk',
        'message', 'ip_address', 'user_agent', 'integrity_hash', 'integrity_ok',
    )
    fieldsets = (
        ('Event', {
            'fields': ('timestamp', 'action', 'model_name', 'object_pk'),
        }),
        ('Actor', {
            'fields': ('user', 'ip_address', 'user_agent'),
        }),
        ('Detail', {
            'fields': ('message',),
        }),
        ('Integrity', {
            'classes': ('collapse',),
            'fields': ('integrity_hash', 'integrity_ok'),
        }),
    )

    @admin.display(description='Action', ordering='action')
    def action_badge(self, obj):
        colour = self._ACTION_COLOURS.get(obj.action, '#343a40')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:bold">{}</span>',
            colour, obj.action,
        )

    @admin.display(description='Message')
    def short_message(self, obj):
        return (obj.message[:80] + '…') if len(obj.message) > 80 else obj.message

    @admin.display(description='✓ Integrity', boolean=True)
    def integrity_ok(self, obj):
        return obj.verify_integrity()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ── Shared colour helpers ──────────────────────────────────────────────────────

def _status_colour(code):
    if code is None:     return '#6c757d'
    if code < 300:       return '#28a745'   # 2xx — green
    if code < 400:       return '#17a2b8'   # 3xx — teal
    if code < 500:       return '#ffc107'   # 4xx — amber
    return '#dc3545'                        # 5xx — red


def _method_colour(method):
    return {
        'GET':    '#17a2b8',
        'POST':   '#28a745',
        'PUT':    '#ffc107',
        'PATCH':  '#fd7e14',
        'DELETE': '#dc3545',
        'HEAD':   '#6c757d',
    }.get(method, '#343a40')


_FLAG_META = {
    # (background, label)
    'NORMAL':     ('#6c757d', 'NORMAL'),
    'SLOW':       ('#fd7e14', 'SLOW  ⏱'),
    'WARNING':    ('#ffc107', 'WARN  404'),
    'SUSPICIOUS': ('#dc3545', 'SUSPICIOUS'),
    'ERROR':      ('#a71d2a', 'ERROR  💥'),
}


# ── Filters ────────────────────────────────────────────────────────────────────

class QuickReviewFilter(admin.SimpleListFilter):
    """One-click shortcuts for the most common review scenarios."""
    title = 'Quick review'
    parameter_name = 'quick'

    def lookups(self, request, model_admin):
        return [
            ('flagged',    'All flagged  (non-normal)'),
            ('errors',     'Server errors  (5xx / exception)'),
            ('suspicious', 'Suspicious  (401 / 403)'),
            ('slow',       'Slow  (> 2 s)'),
            ('not_found',  'Not found  (404)'),
            ('searches',   'Search activity'),
            ('anon',       'Anonymous only'),
        ]

    def queryset(self, request, queryset):
        v = self.value()
        if v == 'flagged':    return queryset.exclude(flag='NORMAL')
        if v == 'errors':     return queryset.filter(flag='ERROR')
        if v == 'suspicious': return queryset.filter(flag='SUSPICIOUS')
        if v == 'slow':       return queryset.filter(flag='SLOW')
        if v == 'not_found':  return queryset.filter(flag='WARNING')
        if v == 'searches':   return queryset.exclude(search_query='')
        if v == 'anon':       return queryset.filter(user__isnull=True)
        return queryset


class StatusCodeFilter(admin.SimpleListFilter):
    title = 'Status range'
    parameter_name = 'status_range'

    def lookups(self, request, model_admin):
        return [
            ('2xx', '2xx — Success'),
            ('3xx', '3xx — Redirect'),
            ('4xx', '4xx — Client error'),
            ('5xx', '5xx — Server error'),
        ]

    def queryset(self, request, queryset):
        v = self.value()
        if v == '2xx': return queryset.filter(status_code__gte=200, status_code__lt=300)
        if v == '3xx': return queryset.filter(status_code__gte=300, status_code__lt=400)
        if v == '4xx': return queryset.filter(status_code__gte=400, status_code__lt=500)
        if v == '5xx': return queryset.filter(status_code__gte=500, status_code__lt=600)
        return queryset


class SlowRequestFilter(admin.SimpleListFilter):
    title = 'Response time'
    parameter_name = 'response_speed'

    def lookups(self, request, model_admin):
        return [
            ('fast',      '< 200 ms'),
            ('medium',    '200 ms – 1 s'),
            ('slow',      '1 s – 3 s'),
            ('very_slow', '> 3 s'),
        ]

    def queryset(self, request, queryset):
        v = self.value()
        if v == 'fast':      return queryset.filter(response_ms__lt=200)
        if v == 'medium':    return queryset.filter(response_ms__gte=200, response_ms__lt=1000)
        if v == 'slow':      return queryset.filter(response_ms__gte=1000, response_ms__lt=3000)
        if v == 'very_slow': return queryset.filter(response_ms__gte=3000)
        return queryset


# ── ActivityLogAdmin ───────────────────────────────────────────────────────────

@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    """
    Full read-only request log for systematic review and problem detection.

    Columns:
      timestamp | FLAG | user | METHOD | path (+ query) | STATUS | ms | IP | view

    Quick review filter (left panel):
      Flagged / Errors / Suspicious / Slow / 404 / Searches / Anonymous

    Use-cases:
      • Security review  — filter "Suspicious" to see all 401/403 (access-denied)
      • Bug hunting      — filter "Errors" to see every 500 + exception class name
      • Performance      — filter "Slow" to find views > 2 s
      • User behaviour   — filter by user to replay their session path-by-path
      • Search analytics — filter "Search activity" to see every query term used
    """

    list_display = (
        'timestamp',
        'flag_badge',
        'user',
        'method_badge',
        'path_display',
        'status_badge',
        'response_ms_display',
        'ip_address',
        'view_name',
        'exception_display',
    )
    list_filter = (
        QuickReviewFilter,
        'method',
        StatusCodeFilter,
        SlowRequestFilter,
        'flag',
    )
    search_fields = (
        'user__username',
        'path',
        'query_string',
        'search_query',
        'view_name',
        'ip_address',
        'user_agent',
        'referer',
        'session_key',
        'exception_type',
        'exception_message',
    )
    date_hierarchy  = 'timestamp'
    ordering        = ('-timestamp',)
    list_per_page   = 50
    show_full_result_count = False   # skip slow COUNT(*) on large tables

    readonly_fields = (
        'timestamp', 'user', 'session_key',
        'method', 'path', 'query_string', 'search_query',
        'view_name', 'referer',
        'status_code', 'response_ms',
        'ip_address', 'user_agent',
        'flag', 'exception_type', 'exception_message',
    )
    fieldsets = (
        ('Classification', {
            'fields': ('flag', 'timestamp'),
        }),
        ('Request', {
            'fields': ('method', 'path', 'query_string', 'search_query', 'view_name', 'referer'),
        }),
        ('Actor', {
            'fields': ('user', 'session_key', 'ip_address', 'user_agent'),
        }),
        ('Response', {
            'fields': ('status_code', 'response_ms'),
        }),
        ('Error detail', {
            # Collapsed by default — only relevant for ERROR flag entries.
            'classes': ('collapse',),
            'fields': ('exception_type', 'exception_message'),
            'description': (
                'Populated only for requests that raised an uncaught Python exception '
                '(FLAG = ERROR). Empty for all other flag levels.'
            ),
        }),
    )

    # ── Computed columns ───────────────────────────────────────────────────────

    @admin.display(description='Flag', ordering='flag')
    def flag_badge(self, obj):
        bg, label = _FLAG_META.get(obj.flag, ('#6c757d', obj.flag))
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:bold;white-space:nowrap">{}</span>',
            bg, label,
        )

    @admin.display(description='Method', ordering='method')
    def method_badge(self, obj):
        colour = _method_colour(obj.method)
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 7px;'
            'border-radius:4px;font-size:11px;font-weight:bold">{}</span>',
            colour, obj.method,
        )

    @admin.display(description='Path  +  query', ordering='path')
    def path_display(self, obj):
        qs      = f'?{obj.query_string}' if obj.query_string else ''
        full    = obj.path + qs
        display = (full[:72] + '…') if len(full) > 72 else full
        # Highlight search queries inline so reviewers see them at a glance.
        if obj.search_query:
            return format_html(
                '<span title="{}">{}'
                '&nbsp;<span style="background:#fff3cd;color:#856404;'
                'border-radius:3px;padding:0 4px;font-size:11px" title="search query">'
                '🔍 {}</span></span>',
                full, display, obj.search_query,
            )
        return format_html('<span title="{}">{}</span>', full, display)

    @admin.display(description='Status', ordering='status_code')
    def status_badge(self, obj):
        colour = _status_colour(obj.status_code)
        code   = obj.status_code or '—'
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:bold">{}</span>',
            colour, code,
        )

    @admin.display(description='Time (ms)', ordering='response_ms')
    def response_ms_display(self, obj):
        if obj.response_ms is None:
            return '—'
        ms = obj.response_ms
        if   ms >= 3000: colour = '#dc3545'
        elif ms >= 1000: colour = '#fd7e14'
        elif ms >= 200:  colour = '#ffc107'
        else:            colour = '#28a745'
        return format_html(
            '<span style="color:{};font-weight:bold">{} ms</span>',
            colour, ms,
        )

    @admin.display(description='Exception')
    def exception_display(self, obj):
        if not obj.exception_type:
            return ''
        tip = obj.exception_message[:200] if obj.exception_message else ''
        return format_html(
            '<span style="background:#a71d2a;color:#fff;padding:2px 6px;'
            'border-radius:4px;font-size:11px;font-weight:bold" title="{}">{}</span>',
            tip, obj.exception_type,
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

