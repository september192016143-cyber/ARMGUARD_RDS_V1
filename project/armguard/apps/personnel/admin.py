from django.contrib import admin
from .models import Personnel

class PersonnelAdmin(admin.ModelAdmin):
    exclude = ('duty_type',)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user.username
        obj.updated_by = request.user.username
        super().save_model(request, obj, form, change)

admin.site.register(Personnel, PersonnelAdmin)
