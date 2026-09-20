from common.admin_audit import AuditAdminMixin
from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group
from django.db import transaction
from common.audit import audit_admin
from .models import User


@admin.register(User)
class PlatformUserAdmin(AuditAdminMixin, UserAdmin):
    list_display = ('username', 'nickname', 'auth_kind', 'is_active', 'is_staff', 'date_joined')
    fieldsets = UserAdmin.fieldsets + (('小程序资料', {'fields': ('nickname', 'record_history', 'auth_kind')}),)
    readonly_fields = ('auth_kind',)

    @transaction.atomic
    def user_change_password(self, request, id, form_url=''):
        # Django's dedicated password form bypasses ModelAdmin.save_model.
        request._audit_password_change = True
        try:
            return super().user_change_password(request, id, form_url)
        finally:
            del request._audit_password_change

    def log_change(self, request, obj, message):
        super().log_change(request, obj, message)
        if getattr(request, '_audit_password_change', False):
            audit_admin('admin.password_changed', request.user, obj,
                        action='password_change', changed_fields=['password'])


admin.site.unregister(Group)


@admin.register(Group)
class PlatformGroupAdmin(AuditAdminMixin, GroupAdmin):
    """Group permission edits are privilege changes and require the same audit."""
