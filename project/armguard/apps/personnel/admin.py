from django.contrib import admin
from .models import Personnel

class PersonnelAdmin(admin.ModelAdmin):
    exclude = (
        'duty_type',
        # Deprecated generic magazine fields — replaced by the per-weapon-type fields
        # (pistol_magazine_item_issued / rifle_magazine_item_issued). Hidden from admin
        # to prevent operator confusion; data is still in the DB for backward compat.
        'magazine_item_assigned',
        'magazine_item_assigned_quantity',
        'magazine_item_assigned_timestamp',
        'magazine_item_assigned_by',
        'magazine_item_issued',
        'magazine_item_issued_quantity',
        'magazine_item_issued_timestamp',
        'magazine_item_issued_by',
    )
    search_fields = ('Personnel_ID', 'first_name', 'last_name', 'rank', 'AFSN', 'squadron')

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user.username
        obj.updated_by = request.user.username
        super().save_model(request, obj, form, change)

admin.site.register(Personnel, PersonnelAdmin)
