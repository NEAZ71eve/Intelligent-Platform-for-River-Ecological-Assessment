from .models import AuditLog


def audit(event, actor=None, target_id='', **details):
    safe_keys = {'status', 'code', 'count', 'duration_ms', 'model_version', 'source'}
    return AuditLog.objects.create(event=event, actor=actor if getattr(actor, 'is_authenticated', False) else None,
                                   target_id=str(target_id), details={k: v for k, v in details.items() if k in safe_keys})

