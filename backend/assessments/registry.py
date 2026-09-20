"""Versioned registry; only registration/activation operations change metadata."""
from django.conf import settings
from django.db import transaction

from common.models import AuditLog
from .artifacts import CONFIG_FIELDS, ModelError, read_manifest, safe_path, validate_config, verify_artifact
from .models import DetectionModel
from recognition.models import QueueControl


def snapshot_for(model):
    result = {field: getattr(model, field) for field in CONFIG_FIELDS}
    result.update(id=str(model.pk), config_digest=model.config_digest)
    validate_config(result)
    return result


def registry_lock():
    QueueControl.objects.get_or_create(name='detection_registry')
    return QueueControl.objects.select_for_update().get(name='detection_registry')


def register_detector(manifest_path, activate=False):
    config = read_manifest(settings.ASSESSMENT_MODEL_ROOT, manifest_path)
    # Validate the graph in a short-lived process, not inside the web interpreter.
    from .isolation import execution_lock, run_detection
    with execution_lock(settings.RECOGNITION_LOCK_PATH) as lock_fd:
        if lock_fd is None:
            raise ModelError('MODEL_WORKER_BUSY', '当前有任务运行，请稍后登记模型。')
        validation = dict(config, id='registration')
        run_detection(validation, '', settings.ASSESSMENT_MODEL_ROOT, settings.MEDIA_ROOT,
                  settings.ASSESSMENT_RUN_TIMEOUT_SECONDS, lock_fd, validate_only=True)
    with transaction.atomic():
        registry_lock()
        existing = DetectionModel.objects.filter(name=config['name'], version=config['version']).first()
        if existing:
            if snapshot_for(existing)['config_digest'] != config['config_digest']:
                raise ModelError('MODEL_VERSION_EXISTS', '该名称与版本已有不同配置，请创建新版本。')
            model = existing
        else:
            model = DetectionModel.objects.create(**config)
            AuditLog.objects.create(event='detector.registered', target_id=str(model.pk), details={'checksum': model.checksum, 'config_digest': model.config_digest})
    if activate:
        activate_detector(model.pk)
        model.refresh_from_db()
    return model


def activate_detector(model_id=None, actor=None):
    with transaction.atomic():
        registry_lock()
        model = DetectionModel.objects.select_for_update().get(pk=model_id) if model_id else None
        if model:
            verify_artifact(settings.ASSESSMENT_MODEL_ROOT, snapshot_for(model))
        DetectionModel.objects.filter(enabled=True).update(enabled=False)
        if model:
            DetectionModel.objects.filter(pk=model.pk).update(enabled=True)
        AuditLog.objects.create(event='detector.activated' if model else 'detector.disabled', actor=actor,
                                target_id=str(model.pk) if model else '', details={'config_digest': model.config_digest} if model else {})
    return model


def public_status():
    model = DetectionModel.objects.filter(enabled=True).first()
    disabled = {'enabled': False, 'model_name': None, 'model_version': None, 'labels': [], 'scope': '', 'threshold': None}
    if model is None:
        return disabled
    try:
        snapshot = snapshot_for(model)
        path = safe_path(settings.ASSESSMENT_MODEL_ROOT, snapshot['artifact'])
        if not 0 < path.stat().st_size <= 128 * 1024 * 1024:
            return disabled
    except (ModelError, OSError):
        return disabled
    return {'enabled': True, 'model_name': model.name, 'model_version': model.version,
            'labels': [{'id': item['id'], 'name': item['name']} for item in model.labels if item['id'] in model.preprocessing['supported_class_ids']],
            'scope': model.scope, 'threshold': model.threshold}
