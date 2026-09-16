from django.contrib import admin
from .models import Favorite, Feedback, History, Visit


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'owner', 'status', 'created_at')
    list_filter = ('status',)
    readonly_fields = ('owner', 'body', 'created_at')

    def has_add_permission(self, request):
        return False


for model in (Favorite, History, Visit):
    admin.site.register(model)

