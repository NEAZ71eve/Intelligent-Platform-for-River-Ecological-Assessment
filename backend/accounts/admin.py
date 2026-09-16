from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class PlatformUserAdmin(UserAdmin):
    list_display = ('username', 'nickname', 'auth_kind', 'is_active', 'is_staff', 'date_joined')
    fieldsets = UserAdmin.fieldsets + (('小程序资料', {'fields': ('nickname', 'record_history', 'auth_kind')}),)
    readonly_fields = ('auth_kind',)

