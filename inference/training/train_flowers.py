"""Reproducible frozen-backbone experiment; hold test metrics until selection is frozen."""
import argparse
import gc
import hashlib
import json
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ.setdefault('OMP_NUM_THREADS', '2')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '2')
os.environ.setdefault('MKL_NUM_THREADS', '2')

import numpy as np
import torch
from PIL import Image, ImageOps
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from torchvision.models import (EfficientNet_B0_Weights, MobileNet_V3_Small_Weights,
                                efficientnet_b0, mobilenet_v3_small)
from recognition.adapter import create_session, preprocess, validate_graph

torch.set_num_threads(2)
torch.set_num_interop_threads(1)
torch.manual_seed(20260916)
torch.hub.set_dir(str(ROOT / '.runtime/torch-cache/hub'))
DATA = ROOT / 'inference/data'
REPORTS = ROOT / 'inference/reports'
CACHE = ROOT / '.runtime/flower-experiment-v1'
ARTIFACTS = ROOT / 'inference/artifacts'
for directory in (REPORTS, CACHE, ARTIFACTS):
    directory.mkdir(parents=True, exist_ok=True)
EXPERIMENT = json.loads((DATA / 'experiment_v1.json').read_text())
SPLIT = json.loads((DATA / 'flowers_split_v1.json').read_text())
ROWS = SPLIT['images']
LABELS = SPLIT['labels']
PREP = EXPERIMENT['preprocessing']
MODELS = EXPERIMENT['models']


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def backbone(name):
    if name == 'mobilenet_v3_small':
        model = mobilenet_v3_small(weights=MobileNet_V3_Small_Weights.IMAGENET1K_V1)
        weight_name = 'mobilenet_v3_small-047dcff4.pth'
    else:
        model = efficientnet_b0(weights=EfficientNet_B0_Weights.IMAGENET1K_V1)
        weight_name = 'efficientnet_b0_rwightman-7f5810bc.pth'
    weight_path = ROOT / '.runtime/torch-cache/hub/checkpoints' / weight_name
    checksum = digest(weight_path)
    if not checksum.startswith(weight_name.rsplit('-', 1)[1].split('.')[0]):
        raise ValueError('Pretrained weight checksum does not match the published filename')
    model.classifier = torch.nn.Identity()
    model.eval().requires_grad_(False)
    return model, {'url': 'https://download.pytorch.org/models/' + weight_name, 'sha256': checksum}


def tensor_for(row):
    path = ROOT / '.runtime/datasets/flower_photos' / row['path']
    if digest(path) != row['sha256']:
        raise ValueError('Dataset changed after split freeze: ' + row['path'])
    with Image.open(path) as image:
        return preprocess(ImageOps.exif_transpose(image).convert('RGB'), PREP)


def softmax(logits):
    logits = logits.astype(np.float64)
    exp = np.exp(logits - logits.max(axis=1, keepdims=True))
    return exp / exp.sum(axis=1, keepdims=True)


def metrics(y, logits, threshold):
    scores = softmax(logits)
    predicted = scores.argmax(axis=1)
    accepted = scores.max(axis=1) >= threshold
    return {
        'samples': len(y), 'accuracy': float(accuracy_score(y, predicted)),
        'macro_f1': float(f1_score(y, predicted, average='macro', labels=range(5), zero_division=0)),
        'confusion_matrix_true_rows_predicted_columns': confusion_matrix(y, predicted, labels=range(5)).tolist(),
        'threshold': threshold, 'accepted_samples': int(accepted.sum()), 'coverage': float(accepted.mean()),
        'accepted_accuracy': float(accuracy_score(y[accepted], predicted[accepted])) if accepted.any() else None,
    }


def peak_mb():
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return raw / (1024**2 if platform.system() == 'Darwin' else 1024)


def fit(name):
    started = time.monotonic()
    feature_path = CACHE / (name + '-features.npz')
    key = digest(DATA / 'flowers_split_v1.json') + ':' + digest(DATA / 'experiment_v1.json')
    model, provenance = backbone(name)
    if feature_path.exists():
        saved = np.load(feature_path, allow_pickle=False)
        if saved['cache_key'].item() != key:
            raise ValueError('Feature cache belongs to a different experiment')
        features = saved['features']
    else:
        batches = []
        with torch.inference_mode():
            for start in range(0, len(ROWS), 16):
                inputs = np.concatenate([tensor_for(row) for row in ROWS[start:start + 16]])
                batches.append(model(torch.from_numpy(inputs)).numpy())
                if start % 320 == 0:
                    print(f'{name}: features {start}/{len(ROWS)} ({time.monotonic()-started:.1f}s)', flush=True)
        features = np.concatenate(batches)
        np.savez_compressed(feature_path, features=features, cache_key=key)
    del model
    gc.collect()
    y = np.array([row['class_index'] for row in ROWS])
    train = np.array([row['split'] == 'train' for row in ROWS])
    validation = np.array([row['split'] == 'validation' for row in ROWS])
    choices, best = [], None
    for c in EXPERIMENT['linear_head_C_candidates']:
        head = LogisticRegression(C=c, solver='lbfgs', max_iter=2000, random_state=EXPERIMENT['seed'])
        head.fit(features[train], y[train])
        logits = head.decision_function(features[validation])
        score = metrics(y[validation], logits, 0.0)
        choices.append({'C': c, 'validation_macro_f1': score['macro_f1'], 'iterations': int(head.n_iter_.max())})
        if best is None or score['macro_f1'] > best[0]:
            best = (score['macro_f1'], head, logits)
    _, head, logits = best
    threshold = 1.0
    for value in np.arange(0, 101) / 100:
        score = metrics(y[validation], logits, float(value))
        if score['accepted_samples'] >= 30 and score['accepted_accuracy'] >= 0.9:
            threshold = float(value)
            break
    np.savez_compressed(CACHE / (name + '-head.npz'), weights=head.coef_.astype(np.float32), bias=head.intercept_.astype(np.float32), threshold=threshold)
    report = {'model': name, 'pretrained': provenance, 'strategy': EXPERIMENT['strategy'],
              'hyperparameters': choices, 'selected_C': head.C, 'threshold': threshold,
              'validation': metrics(y[validation], logits, threshold),
              'fit_seconds': time.monotonic() - started, 'training_process_peak_rss_mb': peak_mb(),
              'split_sha256': digest(DATA / 'flowers_split_v1.json'), 'experiment_sha256': digest(DATA / 'experiment_v1.json')}
    write(REPORTS / (name + '-validation.json'), report)
    print(json.dumps({'fit_complete': name, 'validation': report['validation']}, ensure_ascii=False), flush=True)


def freeze_selection():
    reports = [json.loads((REPORTS / (name + '-validation.json')).read_text()) for name in MODELS]
    # No tie occurred in this experiment; if there is one, require the declared latency tiebreak before testing.
    ranked = sorted(reports, key=lambda report: report['validation']['macro_f1'], reverse=True)
    if ranked[0]['validation']['macro_f1'] == ranked[1]['validation']['macro_f1']:
        raise RuntimeError('Validation tie: benchmark both models and freeze latency tiebreak before testing')
    selection = {'selected_model': ranked[0]['model'], 'basis': 'validation macro F1 only; no test result used',
                 'thresholds': {report['model']: report['threshold'] for report in reports},
                 'validation_report_sha256': {name: digest(REPORTS / (name + '-validation.json')) for name in MODELS},
                 'test_metrics_seen': False}
    path = REPORTS / 'selection_v1.json'
    if path.exists() and json.loads(path.read_text()) != selection:
        raise ValueError('Selection already frozen differently; create a new experiment')
    write(path, selection)
    print('Frozen preferred model: ' + selection['selected_model'], flush=True)


def evaluate(name):
    selection = json.loads((REPORTS / 'selection_v1.json').read_text())
    if digest(REPORTS / (name + '-validation.json')) != selection['validation_report_sha256'][name]:
        raise ValueError('Validation results changed after selection freeze')
    destination = REPORTS / (name + '-test.json')
    if destination.exists():
        raise ValueError('Final test already recorded. Do not tune repeatedly against test data.')
    validation = json.loads((REPORTS / (name + '-validation.json')).read_text())
    saved = np.load(CACHE / (name + '-head.npz'), allow_pickle=False)
    features = np.load(CACHE / (name + '-features.npz'), allow_pickle=False)['features']
    threshold = float(saved['threshold'])
    if threshold != selection['thresholds'][name]:
        raise ValueError('Threshold changed after freeze')
    backbone_model, _ = backbone(name)
    head = torch.nn.Linear(saved['weights'].shape[1], 5)
    with torch.no_grad():
        head.weight.copy_(torch.from_numpy(saved['weights']))
        head.bias.copy_(torch.from_numpy(saved['bias']))
    model = torch.nn.Sequential(backbone_model, head).eval()
    artifact_stem = 'flowers-' + name.replace('_', '-') + '-v1'
    artifact = ARTIFACTS / (artifact_stem + '.onnx')
    torch.onnx.export(model, torch.zeros(1, 3, 224, 224), str(artifact), input_names=['image'], output_names=['logits'],
                      dynamic_axes={'image': {0: 'batch'}, 'logits': {0: 'batch'}}, opset_version=17, dynamo=False)
    blob = artifact.read_bytes()
    validate_graph(blob)
    load_started = time.perf_counter()
    session = create_session(blob)
    load_ms = (time.perf_counter() - load_started) * 1000
    test_indices = [index for index, row in enumerate(ROWS) if row['split'] == 'test']
    logits, max_difference, example = [], 0.0, None
    with torch.inference_mode():
        for start in range(0, len(test_indices), 16):
            indices = test_indices[start:start + 16]
            inputs = np.concatenate([tensor_for(ROWS[index]) for index in indices])
            expected = model(torch.from_numpy(inputs)).numpy()
            actual = session.run(None, {'image': inputs})[0]
            max_difference = max(max_difference, float(np.max(np.abs(actual - expected))))
            logits.append(actual)
            if example is None:
                example = inputs[:1]
    actual = np.concatenate(logits)
    expected_cached = features[test_indices] @ saved['weights'].T + saved['bias']
    labels = np.array([ROWS[index]['class_index'] for index in test_indices])
    for _ in range(5):
        session.run(None, {'image': example})
    times = []
    for _ in range(50):
        begin = time.perf_counter()
        session.run(None, {'image': example})
        times.append((time.perf_counter() - begin) * 1000)
    score = metrics(labels, actual, threshold)
    errors = [{'path': ROWS[index]['path'], 'true': LABELS[int(labels[position])]['id'],
               'predicted': LABELS[int(actual[position].argmax())]['id'], 'score': float(softmax(actual[position:position+1]).max())}
              for position, index in enumerate(test_indices) if actual[position].argmax() != labels[position]]
    report = {'model': name, 'test': score, 'meets_macro_f1_target': score['macro_f1'] >= 0.8,
              'conversion': {'max_absolute_logit_difference': max_difference,
                             'top1_agreement_with_pytorch_cached_features': float((actual.argmax(1) == expected_cached.argmax(1)).mean()),
                             'onnx_macro_f1_minus_pytorch': score['macro_f1'] - metrics(labels, expected_cached, threshold)['macro_f1'], 'quantized': False},
              'artifact': {'filename': artifact.name, 'sha256': digest(artifact), 'size_bytes': artifact.stat().st_size},
              'benchmark': {'provider': 'CPUExecutionProvider', 'threads': 1, 'batch_size': 1, 'warmups': 5, 'iterations': 50,
                            'session_load_ms': load_ms, 'forward_p50_ms': float(np.percentile(times, 50)), 'forward_p95_ms': float(np.percentile(times, 95)),
                            'evaluation_process_peak_rss_mb': peak_mb(), 'memory_scope': 'whole evaluation process with PyTorch and ORT; not isolated serving RSS'},
              'environment': {'platform': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version(), 'torch': torch.__version__},
              'failure_cases': errors, 'limitations': SPLIT['limitations']}
    write(destination, report)
    manifest = {'model_name': 'flowers-' + name.replace('_', '-'), 'model_version': 'v1', 'artifact': artifact.name,
                'sha256': report['artifact']['sha256'], 'labels': LABELS, 'preprocessing': PREP, 'threshold': threshold,
                'scope': EXPERIMENT['scope'], 'license': 'Photos CC-BY-2.0; pretrained weights: see model report',
                'source_url': 'https://www.tensorflow.org/tutorials/load_data/images',
                'evaluation': {'validation': validation['validation'], 'test': score, 'split_sha256': validation['split_sha256'],
                               'pretrained': validation['pretrained'], 'report': f'inference/reports/{name}-test.json'}}
    write(ARTIFACTS / (artifact_stem + '.manifest.json'), manifest)
    print(json.dumps({'test_complete': name, 'test': score, 'benchmark': report['benchmark']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=['fit', 'freeze', 'evaluate', 'all'], default='all')
    parser.add_argument('--model', choices=MODELS)
    args = parser.parse_args()
    if args.stage == 'all':
        for name in MODELS:
            subprocess.run([sys.executable, __file__, '--stage', 'fit', '--model', name], check=True)
        freeze_selection()
        for name in MODELS:
            subprocess.run([sys.executable, __file__, '--stage', 'evaluate', '--model', name], check=True)
    elif args.stage == 'freeze':
        freeze_selection()
    elif args.model:
        (fit if args.stage == 'fit' else evaluate)(args.model)
    else:
        parser.error('--model is required for fit/evaluate')
