"""Detection-specific manifest contract; no Django or inference runtime imports."""
import hashlib
import json
import math
import re
from pathlib import Path

from recognition.artifacts import MAX_MANIFEST_BYTES, MAX_MODEL_BYTES, ModelError, safe_path

CONFIG_FIELDS = ('name', 'version', 'artifact', 'checksum', 'labels', 'preprocessing',
                 'threshold', 'scope', 'license', 'source', 'evaluation')
CATEGORIES = {'floating_debris', 'bloom_blackwater', 'outfall_discharge', 'bank_problem'}


def config_digest(config):
    try:
        fields = {key: config[key] for key in CONFIG_FIELDS}
        fields['threshold'] = float(fields['threshold'])
        raw = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        return hashlib.sha256(raw.encode()).hexdigest()
    except (KeyError, TypeError, ValueError) as exc:
        raise ModelError('MODEL_CONFIG_INVALID') from exc


def validate_config(config):
    try:
        for key, maximum in [('name', 80), ('version', 64), ('scope', 2000), ('license', 100), ('source', 500)]:
            if not isinstance(config[key], str) or not config[key].strip() or len(config[key]) > maximum:
                raise ValueError(key)
        if not re.fullmatch(r'[a-f0-9]{64}', config['checksum']):
            raise ValueError('checksum')
        artifact = config['artifact']
        if not isinstance(artifact, str) or Path(artifact).is_absolute() or '..' in Path(artifact).parts or Path(artifact).suffix != '.onnx':
            raise ValueError('artifact')
        labels = config['labels']
        if not isinstance(labels, list) or not 1 <= len(labels) <= 80:
            raise ValueError('labels')
        for index, label in enumerate(labels):
            if not isinstance(label, dict) or set(label) != {'id', 'name', 'eval_category'}:
                raise ValueError('label')
            if type(label['id']) is not int or label['id'] != index:
                raise ValueError('label id')
            if not isinstance(label['name'], str) or not 1 <= len(label['name']) <= 100:
                raise ValueError('label name')
            if label['eval_category'] not in CATEGORIES:
                raise ValueError('label category')
        prep = config['preprocessing']
        if set(prep) != {'resize_size', 'letterbox', 'pad_value', 'interpolation', 'scale', 'supported_class_ids'}:
            raise ValueError('preprocessing')
        if type(prep['resize_size']) is not int or prep['resize_size'] != 640 or prep['letterbox'] is not True or prep['pad_value'] != 114 or prep['interpolation'] != 'bilinear' or prep['scale'] != [0.0, 1.0]:
            raise ValueError('input contract')
        supported = prep['supported_class_ids']
        if not isinstance(supported, list) or not supported or any(type(i) is not int or not 0 <= i < len(labels) for i in supported) or len(set(supported)) != len(supported):
            raise ValueError('supported classes')
        if any(labels[i]['eval_category'] != 'floating_debris' for i in supported):
            raise ValueError('category has no implemented assessment rule')
        threshold = config['threshold']
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not 0 < threshold <= 1:
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
    digest, blocks, size = hashlib.sha256(), [], 0
    with path.open('rb') as stream:
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
    try:
        root = Path(root).resolve(strict=True)
        relative = Path(manifest_path).resolve(strict=True).relative_to(root)
        path = safe_path(root, str(relative))
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError('manifest too large')
        manifest = json.loads(path.read_text(encoding='utf-8'))
        filename = manifest['artifact']
        if manifest.get('task') != 'detection' or not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError('detection artifact required')
        config = {
            'name': manifest['model_name'], 'version': manifest['model_version'],
            'artifact': (relative.parent / filename).as_posix(), 'checksum': manifest['sha256'],
            'labels': manifest['labels'], 'preprocessing': manifest['preprocessing'],
            'threshold': manifest['threshold'], 'scope': manifest['scope'],
            'license': manifest['license'], 'source': manifest['source_url'], 'evaluation': manifest['evaluation'],
        }
        config['config_digest'] = validate_config(config)
        verify_artifact(root, config)
        return config
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ModelError('MODEL_MANIFEST_INVALID') from exc
