from django.contrib import admin, messages as admin_messages
from .models import Pistol, Rifle, Magazine, Ammunition, Accessory, FirearmDiscrepancy
from .inventory_analytics_model import Inventory_Analytics, AnalyticsSnapshot
from django import forms
from django.contrib.admin import SimpleListFilter
from django.utils import timezone
from datetime import timedelta
from armguard.apps.inventory.inventory_analytics_model import (
    DUTY_TYPE_CHOICES, LOG_STATUS_CHOICES,
)


def _compact_item_numbers(modeladmin, request, queryset):
    """
    Admin action: compact item_number values for all items of the same model
    as the selected items, filling gaps from 0001 upward.
    """
    from django.db import transaction as db_tx
    from utils.item_tag_generator import generate_item_tag

    Model = queryset.model
    # Collect distinct model names touched by the selection
    models_affected = set(queryset.values_list('model', flat=True))
    total_changed = 0

    for model_name in models_affected:
        items = list(Model.objects.filter(model=model_name).order_by('created', 'item_id'))
        to_change = [
            (item, f"{seq:04d}")
            for seq, item in enumerate(items, start=1)
            if item.item_number != f"{seq:04d}"
        ]
        if not to_change:
            continue
        pks = {item.pk for item, _ in to_change}
        with db_tx.atomic():
            Model.objects.filter(pk__in=pks).update(item_number='')
            for item, candidate in to_change:
                Model.objects.filter(pk=item.pk).update(item_number=candidate)
                item.item_number = candidate
                try:
                    generate_item_tag(item)
                except Exception:
                    pass
        total_changed += len(to_change)

    admin_messages.success(
        request,
        f"{total_changed} item number(s) reassigned and tags regenerated."
        if total_changed else "All item numbers are already sequential — nothing to change."
    )


_compact_item_numbers.short_description = "Compact item numbers (fill gaps from 0001)"

class PistolAdmin(admin.ModelAdmin):
    exclude = ('category',)
    list_display = [
        'item_id', 'model', 'serial_number', 'item_status', 'item_condition',
        'item_issued_to', 'item_assigned_to', 'created',
    ]
    list_filter = ['item_status', 'item_condition', 'model']
    search_fields = ['item_id', 'serial_number', 'item_issued_to__Personnel_ID', 'item_assigned_to']
    readonly_fields = ['item_id', 'qr_code', 'item_number', 'remarks_timestamp', 'remarks_updated_by']
    actions = [_compact_item_numbers]

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user.username
        obj.updated_by = request.user.username
        # Stamp remarks audit fields when remarks changes via admin
        if change and 'remarks' in form.changed_data:
            obj.remarks_timestamp = timezone.now()
            obj.remarks_updated_by = request.user.username
        elif not change and obj.remarks:
            obj.remarks_timestamp = timezone.now()
            obj.remarks_updated_by = request.user.username
        super().save_model(request, obj, form, change)

class RifleAdmin(admin.ModelAdmin):
    from .forms import RifleAdminForm
    form = RifleAdminForm
    exclude = ('category',)
    list_display = [
        'item_id', 'model', 'serial_number', 'item_status', 'item_condition',
        'item_issued_to', 'item_assigned_to', 'created',
    ]
    list_filter = ['item_status', 'item_condition', 'model']
    search_fields = ['item_id', 'serial_number', 'item_issued_to__Personnel_ID', 'item_assigned_to']
    readonly_fields = ['item_id', 'qr_code', 'item_number', 'remarks_timestamp', 'remarks_updated_by']
    actions = [_compact_item_numbers]

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user.username
        obj.updated_by = request.user.username
        # Stamp remarks audit fields when remarks changes via admin
        if change and 'remarks' in form.changed_data:
            obj.remarks_timestamp = timezone.now()
            obj.remarks_updated_by = request.user.username
        elif not change and obj.remarks:
            obj.remarks_timestamp = timezone.now()
            obj.remarks_updated_by = request.user.username
        super().save_model(request, obj, form, change)

class MagazineAdminForm(forms.ModelForm):
    class Meta:
        model = Magazine
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'capacity' in self.fields:
            self.fields['capacity'].widget.attrs['readonly'] = True
        # Set initial value if type is already set
        if self.instance and hasattr(self.instance, 'type') and self.instance.type:
            self.fields['capacity'].initial = self._capacity_for_type(self.instance.type)

    class Media:
        js = ('admin/js/magazine_capacity_autofill.js',)

    def _capacity_for_type(self, type_value):
        if type_value == 'Short':
            return '20-rounds'
        elif type_value == 'Long':
            return '30-rounds'
        return ''

class MagazineAdmin(admin.ModelAdmin):
    form = MagazineAdminForm
    exclude = ('category',)
    list_display = ['id', 'type', 'capacity', 'quantity', 'created']
    list_filter = ['type']
    search_fields = ['type']

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user.username
        obj.updated_by = request.user.username
        super().save_model(request, obj, form, change)

class AmmunitionAdmin(admin.ModelAdmin):
    exclude = ('category',)
    list_display = ['id', 'type', 'lot_number', 'quantity', 'created']
    list_filter = ['type']
    search_fields = ['type', 'lot_number']

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user.username
        obj.updated_by = request.user.username
        super().save_model(request, obj, form, change)

class AccessoryAdmin(admin.ModelAdmin):
    exclude = ('category',)
    list_display = ['id', 'type', 'quantity', 'created']
    list_filter = ['type']
    search_fields = ['type']

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user.username
        obj.updated_by = request.user.username
        super().save_model(request, obj, form, change)

admin.site.register(Pistol, PistolAdmin)
admin.site.register(Rifle, RifleAdmin)
admin.site.register(Magazine, MagazineAdmin)
admin.site.register(Ammunition, AmmunitionAdmin)
admin.site.register(Accessory, AccessoryAdmin)
# admin.site.register(Location)  # Disabled temporarily


@admin.register(FirearmDiscrepancy)
class FirearmDiscrepancyAdmin(admin.ModelAdmin):
    list_display  = ['pk', 'firearm_type', 'pistol', 'rifle', 'discrepancy_type',
                     'status', 'reported_by', 'reported_at']
    list_filter   = ['status', 'discrepancy_type']
    search_fields = ['pistol__serial_number', 'rifle__serial_number',
                     'reported_by__username', 'description']
    readonly_fields = ['reported_at', 'firearm_type']
    autocomplete_fields = []

    fieldsets = (
        ('Firearm', {
            'description': 'Set exactly one of Pistol or Rifle.',
            'fields': ('pistol', 'rifle'),
        }),
        ('Personnel', {
            'fields': ('issuer', 'withdrawer', 'related_transaction'),
        }),
        ('Discrepancy Details', {
            'fields': ('discrepancy_type', 'description', 'status'),
        }),
        ('Reporting', {
            'fields': ('reported_by', 'reported_at'),
        }),
        ('Resolution', {
            'fields': ('resolved_by', 'resolved_at', 'resolution_notes'),
            'classes': ('collapse',),
        }),
    )

    def save_model(self, request, obj, form, change):
        if not obj.reported_by_id:
            obj.reported_by = request.user
        super().save_model(request, obj, form, change)


class InventoryAnalyticsAdmin(admin.ModelAdmin):

    class DateRangeFilter(SimpleListFilter):
        """Sidebar filter that scopes counts by transaction date."""
        title = 'Date range'
        parameter_name = 'date_range'

        def lookups(self, request, model_admin):
            return [
                ('today',  'Today'),
                ('week',   'This Week'),
                ('month',  'This Month'),
            ]

        def queryset(self, request, queryset):
            return queryset  # handled in changelist_view

    class DutyTypeFilter(SimpleListFilter):
        """Sidebar filter that scopes counts by duty type."""
        title = 'Duty type'
        parameter_name = 'duty_type'

        def lookups(self, request, model_admin):
            return DUTY_TYPE_CHOICES

        def queryset(self, request, queryset):
            return queryset  # handled in changelist_view

    class LogStatusFilter(SimpleListFilter):
        """Sidebar filter that scopes counts to transactions whose Transaction Log
        has the selected status (Open / Partially Returned / Closed)."""
        title = 'Log status'
        parameter_name = 'log_status'

        def lookups(self, request, model_admin):
            return LOG_STATUS_CHOICES

        def queryset(self, request, queryset):
            return queryset  # handled in changelist_view

    list_display = [
        'item_type', 'weapon_type', 'category',
        'total_count', 'issued_count', 'available_count',
        'par_count', 'tr_count', 'last_updated',
    ]
    list_filter  = ['item_type', 'weapon_type', DateRangeFilter, DutyTypeFilter, LogStatusFilter]
    search_fields = ['category']
    readonly_fields = [
        'item_type', 'weapon_type', 'category',
        'total_count', 'issued_count', 'available_count',
        'par_count', 'tr_count', 'last_updated',
    ]
    fieldsets = (
        (None, {
            'fields': ('item_type', 'weapon_type', 'category'),
        }),
        ('Counts', {
            'fields': ('total_count', 'issued_count', 'available_count'),
        }),
        ('Issuance Type Counts', {
            'fields': ('par_count', 'tr_count'),
        }),
        ('Meta', {
            'fields': ('last_updated',),
        }),
    )

    # Disable all write operations — analytics is read-only / auto-generated
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        """Auto-refresh analytics on every page load, applying any active sidebar filters."""
        now = timezone.now()
        # Date range
        date_range = request.GET.get('date_range')
        if date_range == 'today':
            date_from = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_range == 'week':
            date_from = (now - timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        elif date_range == 'month':
            date_from = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            date_from = None
        # Duty type & log status
        duty_type  = request.GET.get('duty_type') or None
        log_status = request.GET.get('log_status') or None
        Inventory_Analytics.sync_from_inventory(
            date_from=date_from,
            duty_type=duty_type,
            log_status=log_status,
        )
        return super().changelist_view(request, extra_context=extra_context)


admin.site.register(Inventory_Analytics, InventoryAnalyticsAdmin)


@admin.register(AnalyticsSnapshot)
class AnalyticsSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        'snapshot_date', 'item_type', 'weapon_type', 'category',
        'total_count', 'issued_count', 'available_count',
        'par_count', 'tr_count', 'taken_at',
    ]
    list_filter  = ['snapshot_date', 'item_type', 'weapon_type']
    search_fields = ['category']
    date_hierarchy = 'snapshot_date'
    readonly_fields = [
        'snapshot_date', 'item_type', 'weapon_type', 'category',
        'total_count', 'issued_count', 'available_count',
        'par_count', 'tr_count', 'taken_at',
    ]

    actions = ['delete_snapshot_date']

    @admin.action(description='Delete all snapshots for the selected date(s)')
    def delete_snapshot_date(self, request, queryset):
        dates = queryset.values_list('snapshot_date', flat=True).distinct()
        from .inventory_analytics_model import AnalyticsSnapshot
        count, _ = AnalyticsSnapshot.objects.filter(snapshot_date__in=dates).delete()
        self.message_user(request, f"Deleted {count} snapshot row(s) across {len(list(dates))} date(s).")

    def has_add_permission(self, request):              return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return True
