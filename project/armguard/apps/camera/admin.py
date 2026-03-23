from django.contrib import admin
from django.utils.html import format_html
from .models import CameraDevice, CameraUploadLog


@admin.register(CameraDevice)
class CameraDeviceAdmin(admin.ModelAdmin):
    list_display  = ('user', 'device_name', 'status_badge', 'paired_at', 'activated_at', 'last_seen_at', 'failed_attempts')
    list_filter   = ('is_active',)
    search_fields = ('user__username', 'device_name')
    readonly_fields = (
        'device_token', 'device_fingerprint',
        'paired_at', 'activated_at', 'last_seen_at',
        'revoked_at', 'revoked_by', 'failed_attempts', 'locked_until',
    )
    fields = (
        'user', 'device_name', 'is_active',
        'device_token', 'device_fingerprint',
        'paired_at', 'activated_at', 'last_seen_at',
        'revoked_at', 'revoked_by',
        'failed_attempts', 'locked_until',
    )

    @admin.display(description='Status')
    def status_badge(self, obj):
        if obj.revoked_at:
            return format_html('<span style="color:#ef4444;">&#9632; Revoked</span>')
        if obj.is_active:
            return format_html('<span style="color:#22c55e;">&#9679; Active</span>')
        return format_html('<span style="color:#f59e0b;">&#9203; Pending</span>')


@admin.register(CameraUploadLog)
class CameraUploadLogAdmin(admin.ModelAdmin):
    list_display  = ('uploaded_at', 'uploaded_by', 'device', 'original_name', 'file_size_bytes', 'ip_address')
    list_filter   = ('uploaded_at',)
    search_fields = ('uploaded_by__username', 'original_name', 'stored_name')
    readonly_fields = ('uploaded_by', 'device', 'original_name', 'stored_name', 'file_path', 'file_size_bytes', 'uploaded_at', 'ip_address')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
