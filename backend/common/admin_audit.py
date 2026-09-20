"""Content-free admin auditing, atomic with the operation being recorded."""
from django.db import transaction

from .audit import audit_admin


class AuditAdminMixin:
    # Existing custom actions audit in their business service. Wrapping actions here
    # would report failed/preview operations as changes and double-count successes.
    @transaction.atomic
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        audit_admin('admin.changed' if change else 'admin.added', request.user,
                    obj, action='change' if change else 'add',
                    changed_fields=form.changed_data)

    @transaction.atomic
    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        for obj, fields in formset.changed_objects:
            audit_admin('admin.inline_changed', request.user, obj,
                        action='change', changed_fields=fields)
        for obj in formset.new_objects:
            audit_admin('admin.inline_added', request.user, obj, action='add')
        # Django clears deleted model primary keys after save(); capture them in
        # delete_existing so inline deletes remain attributable without body values.
        for model, pk in getattr(formset, '_audit_deleted_objects', []):
            audit_admin('admin.inline_deleted', request.user, model,
                        action='delete', target_id=pk)

    def get_formsets_with_inlines(self, request, obj=None):
        for formset_class, inline in super().get_formsets_with_inlines(request, obj):
            class AuditedFormSet(formset_class):
                def delete_existing(self, instance, commit=True):
                    if commit:
                        if not hasattr(self, '_audit_deleted_objects'):
                            self._audit_deleted_objects = []
                        self._audit_deleted_objects.append((type(instance), str(instance.pk)))
                    return super().delete_existing(instance, commit)
            yield AuditedFormSet, inline

    @transaction.atomic
    def delete_model(self, request, obj):
        # Write before delete: SET_NULL also handles an administrator deleting self.
        audit_admin('admin.deleted', request.user, obj, action='delete')
        super().delete_model(request, obj)

    @transaction.atomic
    def delete_queryset(self, request, queryset):
        # Freeze the authorized selection. Re-running a mutable filter could delete
        # rows that appeared after the audit pass, or leave audited rows untouched.
        ids = list(queryset.select_for_update().order_by('pk').values_list('pk', flat=True))
        for pk in ids:
            audit_admin('admin.bulk_deleted', request.user, self.model,
                        action='bulk_delete', target_id=pk)
        super().delete_queryset(request, self.model._base_manager.using(queryset.db).filter(pk__in=ids))
