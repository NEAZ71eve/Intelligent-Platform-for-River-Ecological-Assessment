from .models import AuditLog


def audit(event, actor=None, target_id='', **details):
    safe_keys = {'status', 'code', 'count', 'duration_ms', 'model_version', 'source'}
    return AuditLog.objects.create(event=event, actor=actor if getattr(actor, 'is_authenticated', False) else None,
                                   target_id=str(target_id), details={k: v for k, v in details.items() if k in safe_keys})


def audit_admin(event, actor, obj, *, action, changed_fields=(), target_id=None, **details):
    """Record structure, never field values. Caller owns the mutation transaction.

    Inserting in the same transaction makes the audit visible only on commit and
    fails closed if logging fails. Rollbacks remove both the mutation and its log.
    """
    meta = obj._meta
    allowed_names = {field.name for field in meta.get_fields() if not field.auto_created}
    fields = sorted(set(changed_fields) & allowed_names)
    record = audit(event, actor, target_id if target_id is not None else obj.pk, **details)
    record.model_label = meta.label_lower
    record.action = action
    record.changed_fields = fields
    record.save(update_fields=['model_label', 'action', 'changed_fields'])
    return record
