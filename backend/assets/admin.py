from common.admin_audit import AuditAdminMixin
from django.contrib import admin
from .models import Asset


@admin.register(Asset)
class AssetAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'owner', 'purpose', 'byte_size', 'created_at', 'expires_at')
    list_filter = ('purpose',)
    exclude = ('original', 'thumbnail')
    readonly_fields = ('id', 'owner', 'purpose', 'width', 'height', 'byte_size', 'created_at', 'original_expires_at', 'expires_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

