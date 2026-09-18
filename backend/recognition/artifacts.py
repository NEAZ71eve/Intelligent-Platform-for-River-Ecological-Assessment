"""Pure Python artifact contract. This module never initializes Django or ORT."""
import hashlib
import json
import math
import re
import stat
from pathlib import Path

MAX_MODEL_BYTES = 128 * 1024 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
CONFIG_FIELDS = ('name', 'version', 'artifact', 'checksum', 'labels', 'preprocessing', 'threshold', 'scope', 'license', 'source', 'evaluation')


class ModelError(Exception):
    def __init__(self, code, message='模型配置或推理失败'):
        self.code = code
        super().__init__(message)


def config_digest(config):
    try:
        values = {key: config[key] for key in CONFIG_FIELDS}
        # FloatField round-trips 1 as 1.0; equivalent thresholds need identical digests.
        values['threshold'] = float(values['threshold'])
        raw = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (KeyError, TypeError, ValueError) as exc:
        raise ModelError('MODEL_CONFIG_INVALID') from exc
    return hashlib.sha256(raw.encode()).hexdigest()


def safe_path(root, value):
    root = Path(root).resolve(strict=True)
    candidate = Path(value)
    if candidate.is_absolute() or '..' in candidate.parts:
        raise ModelError('MODEL_PATH_INVALID')
    try:
        path = (root / candidate).resolve(strict=True)
        if not path.is_relative_to(root) or not stat.S_ISREG(path.stat().st_mode):
            raise ModelError('MODEL_PATH_INVALID')
    except (OSError, RuntimeError) as exc:
        raise ModelError('MODEL_FILE_MISSING') from exc
    return path


def validate_config(config):
    try:
        for field, maximum in [('name', 80), ('version', 64), ('scope', 2000), ('license', 100), ('source', 500)]:
            if not isinstance(config[field], str) or not config[field].strip() or len(config[field]) > maximum:
                raise ValueError(field)
        if not re.fullmatch(r'[a-f0-9]{64}', config['checksum']):
            raise ValueError('checksum')
        artifact = config['artifact']
        if not isinstance(artifact, str) or Path(artifact).is_absolute() or '..' in Path(artifact).parts or Path(artifact).suffix != '.onnx':
            raise ValueError('artifact')
        labels = config['labels']
        if not isinstance(labels, list) or not 1 <= len(labels) <= 100:
            raise ValueError('labels required')
        ids = set()
        for label in labels:
            if not isinstance(label, dict) or set(label) - {'id', 'name', 'fine', 'eval_category'}:
                raise ValueError('label')
            if isinstance(label['id'], bool) or not isinstance(label['id'], int) or label['id'] < 0 or label['id'] in ids:
                raise ValueError('label id')
            if not isinstance(label['name'], str) or not 1 <= len(label['name']) <= 100:
                raise ValueError('label name')
            if not isinstance(label.get('fine'), str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', label['fine']):
                raise ValueError('fine label')
            if not isinstance(label.get('eval_category'), str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', label['eval_category']):
                raise ValueError('eval category')
            ids.add(label['id'])
        prep = config['preprocessing']
        if set(prep) != {'resize_size', 'letterbox', 'pad_value', 'interpolation', 'scale'}:
            raise ValueError('preprocessing')
        if prep['resize_size'] != 640 or prep['letterbox'] is not True or prep['pad_value'] != 114 or prep['interpolation'] != 'bilinear' or prep['scale'] != [0.0, 1.0]:
            raise ValueError('image contract')
        threshold = config['threshold']
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError('threshold')
        if not isinstance(config['evaluation'], dict):
            raise ValueError('evaluation')
        digest = config_digest(config)
        if config.get('config_digest', digest) != digest:
            raise ModelError('MODEL_CONFIG_MISMATCH')
        return digest
    except (KeyError, TypeError, ValueError) as exc:
        raise ModelError('MODEL_CONFIG_INVALID') from exc


def verify_artifact(root, config, *, return_bytes=False):
    validate_config(config)
    path = safe_path(root, config['artifact'])
    digest = hashlib.sha256()
    blocks = []
    with path.open('rb') as stream:
        size = 0
        while block := stream.read(1024 * 1024):
            size += len(block)
            if size > MAX_MODEL_BYTES:
                raise ModelError('MODEL_TOO_LARGE')
            digest.update(block)
            if return_bytes:
                blocks.append(block)
    if not size or digest.hexdigest() != config['checksum']:
        raise ModelError('MODEL_CHECKSUM_MISMATCH')
    return b''.join(blocks) if return_bytes else path


def read_manifest(root, manifest_path):
    root = Path(root).resolve(strict=True)
    try:
        given = Path(manifest_path).resolve(strict=True)
        relative = given.relative_to(root)
        path = safe_path(root, str(relative))
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError('manifest too large')
        manifest = json.loads(path.read_text(encoding='utf-8'))
        filename = manifest['artifact']
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError('artifact must be a filename relative to manifest')
        config = {
            'name': manifest['model_name'], 'version': manifest['model_version'],
            'artifact': str((relative.parent / filename).as_posix()), 'checksum': manifest['sha256'],
            'labels': manifest['labels'], 'preprocessing': manifest['preprocessing'],
            'threshold': manifest['threshold'], 'scope': manifest['scope'],
            'license': manifest['license'], 'source': manifest['source_url'], 'evaluation': manifest['evaluation'],
        }
        config['config_digest'] = validate_config(config)
        verify_artifact(root, config)
        return config
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ModelError('MODEL_MANIFEST_INVALID') from exc
