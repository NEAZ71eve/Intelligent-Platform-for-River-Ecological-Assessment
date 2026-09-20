"""Synthetic ONNX tests verify detection contracts, not recognition accuracy."""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from django.test import SimpleTestCase, TestCase, override_settings
from onnx import TensorProto, helper, numpy_helper
from PIL import Image

from recognition.artifacts import ModelError
from recognition.models import ModelVersion
from .artifacts import config_digest, read_manifest, validate_config, verify_artifact
from .detector import infer, preprocess, validate_graph, validate_output
from .isolation import execution_lock, run_detection
from .models import DetectionModel
from .registry import activate_detector, public_status, register_detector, snapshot_for


def synthetic_output():
    # Supported class 1 has two overlapping boxes; reserved class 0 must disappear.
    return np.asarray([[[320, 322, 50], [320, 322, 50], [200, 200, 30], [120, 120, 30],
                        [0.01, 0.01, 0.99], [0.9, 0.8, 0.01]]], dtype=np.float32)


def synthetic_model(raw=None):
    raw = synthetic_output() if raw is None else raw
    graph = helper.make_graph(
        [helper.make_node('Constant', [], ['detections'], value=numpy_helper.from_array(raw))],
        'synthetic-detection-contract-only',
        [helper.make_tensor_value_info('images', TensorProto.FLOAT, [1, 3, 640, 640])],
        [helper.make_tensor_value_info('detections', TensorProto.FLOAT, list(raw.shape))])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid('', 13)])
    model.ir_version = 10
    return model


class RuntimeFixture:
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(prefix='hyhq-detector-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.media = self.root / 'media'
        self.media.mkdir()
        self.lock = self.root / 'execution.lock'
        self.override = override_settings(ASSESSMENT_MODEL_ROOT=self.root, MEDIA_ROOT=self.media,
                                         RECOGNITION_LOCK_PATH=self.lock, ASSESSMENT_RUN_TIMEOUT_SECONDS=10)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.artifact = self.root / 'detector.onnx'
        self.artifact.write_bytes(synthetic_model().SerializeToString())
        self.manifest_data = {
            'model_name': 'synthetic-detector', 'model_version': 'test-v1', 'task': 'detection',
            'artifact': self.artifact.name, 'sha256': hashlib.sha256(self.artifact.read_bytes()).hexdigest(),
            'labels': [{'id': 0, 'name': 'Reserved', 'eval_category': 'outfall_discharge'},
                       {'id': 1, 'name': 'Synthetic debris', 'eval_category': 'floating_debris'}],
            'preprocessing': {'resize_size': 640, 'letterbox': True, 'pad_value': 114,
                              'interpolation': 'bilinear', 'scale': [0.0, 1.0], 'supported_class_ids': [1]},
            'threshold': 0.5, 'scope': 'Synthetic fixture; no accuracy claim.',
            'license': 'CC0 test fixture', 'source_url': 'https://example.org/fixture', 'evaluation': {'fixture': True},
        }
        self.manifest = self.root / 'manifest.json'
        self.write_manifest()
        y, x = np.indices((96, 128))
        self.image = self.media / 'gradient.png'
        Image.fromarray(np.stack((x * 2, y * 2, (x + y) % 256), axis=-1).astype(np.uint8)).save(self.image)

    def write_manifest(self):
        self.manifest.write_text(json.dumps(self.manifest_data), encoding='utf-8')

    def snapshot(self):
        return dict(read_manifest(self.root, self.manifest), id='synthetic')


class DetectionRuntimeTests(RuntimeFixture, SimpleTestCase):
    def test_real_onnx_inference_filters_reserved_head_and_overlapping_box(self):
        result = infer(self.snapshot(), self.image, self.root, self.media)
        self.assertEqual(result['decision'], 'detected')
        self.assertEqual((result['image_width'], result['image_height']), (128, 96))
        self.assertEqual(len(result['detections']), 1)
        box = result['detections'][0]
        self.assertEqual(box['class_id'], 1)
        self.assertAlmostEqual(box['confidence'], 0.9, places=6)
        self.assertEqual(box['bbox'], [44.0, 36.0, 84.0, 60.0])

    def test_quality_and_no_detection_are_uncertain(self):
        Image.new('RGB', (80, 80), 'green').save(self.image)
        result = infer(self.snapshot(), self.image, self.root, self.media)
        self.assertEqual((result['decision'], result['reason'], result['detections']),
                         ('uncertain', 'LOW_IMAGE_QUALITY', []))
        Image.effect_noise((80, 80), 100).convert('RGB').save(self.image)
        snapshot = self.snapshot()
        snapshot['threshold'] = 0.95
        snapshot['config_digest'] = config_digest(snapshot)
        result = infer(snapshot, self.image, self.root, self.media)
        self.assertEqual((result['decision'], result['reason'], result['detections']),
                         ('uncertain', 'NO_SUPPORTED_DETECTIONS', []))

    def test_supported_categories_and_digest_are_enforced(self):
        snapshot = self.snapshot()
        snapshot['preprocessing']['supported_class_ids'] = [0]
        snapshot.pop('config_digest')
        with self.assertRaisesRegex(ModelError, '模型配置') as caught:
            validate_config(snapshot)
        self.assertEqual(caught.exception.code, 'MODEL_CONFIG_INVALID')
        snapshot = self.snapshot()
        snapshot['threshold'] = 0.8
        with self.assertRaises(ModelError) as caught:
            verify_artifact(self.root, snapshot)
        self.assertEqual(caught.exception.code, 'MODEL_CONFIG_MISMATCH')

    def test_manifest_task_checksum_and_path_are_enforced(self):
        for key, value in [('task', 'classification'), ('artifact', '../detector.onnx'), ('sha256', '0' * 64)]:
            original = self.manifest_data[key]
            self.manifest_data[key] = value
            self.write_manifest()
            with self.assertRaises(ModelError):
                read_manifest(self.root, self.manifest)
            self.manifest_data[key] = original

    def test_malformed_outputs_fail_closed(self):
        for raw in [np.zeros((1, 6, 30001), np.float32), np.zeros((1, 5, 3), np.float32),
                    np.zeros((1, 6, 3), np.float64), np.full((1, 6, 3), np.nan, np.float32)]:
            with self.assertRaises(ModelError):
                validate_output(raw, 2)
        raw = synthetic_output()
        raw[0, 4, 0] = 1.1
        with self.assertRaises(ModelError):
            validate_output(raw, 2)

    def test_zero_width_and_out_of_image_boxes_do_not_survive(self):
        raw = synthetic_output()
        raw[0, 2, 0] = 0
        raw[0, 0, 1] = -1000
        snapshot = self.snapshot()
        with patch('assessments.detector._run', return_value=raw):
            result = infer(snapshot, self.image, self.root, self.media)
        self.assertEqual(result['detections'], [])

    def test_subpixel_box_preserves_positive_width(self):
        raw = synthetic_output()[:, :, :1].copy()
        raw[0, 2, 0] = 0.0001
        with patch('assessments.detector._run', return_value=raw):
            result = infer(self.snapshot(), self.image, self.root, self.media)
        box = result['detections'][0]['bbox']
        self.assertGreater(box[2], box[0])

    def test_extreme_aspect_ratio_preprocessing_keeps_positive_dimensions(self):
        pixels, transform = preprocess(Image.new('RGB', (1, 2048)))
        self.assertEqual(pixels.shape, (1, 3, 640, 640))
        self.assertGreater(transform[0], 0)
        self.assertTrue(np.isfinite(pixels).all())

    def test_model_graph_rejects_custom_ops_and_wrong_dimensions(self):
        model = synthetic_model()
        model.graph.node[0].domain = 'custom'
        with self.assertRaises(ModelError) as caught:
            validate_graph(model.SerializeToString(), 2)
        self.assertEqual(caught.exception.code, 'MODEL_CUSTOM_OP_FORBIDDEN')
        model = synthetic_model()
        model.graph.input[0].type.tensor_type.shape.dim[2].dim_value = 224
        with self.assertRaises(ModelError):
            validate_graph(model.SerializeToString(), 2)
        model = synthetic_model()
        tensor = model.graph.node[0].attribute[0].t
        tensor.data_location = TensorProto.EXTERNAL
        with self.assertRaises(ModelError) as caught:
            validate_graph(model.SerializeToString(), 2)
        self.assertEqual(caught.exception.code, 'MODEL_EXTERNAL_DATA_FORBIDDEN')

    def test_real_subprocess_validates_and_runs_same_protocol(self):
        with execution_lock(self.lock) as fd:
            self.assertEqual(run_detection(self.snapshot(), '', self.root, self.media, 10, fd, validate_only=True), {'validated': True})
            result = run_detection(self.snapshot(), self.image, self.root, self.media, 10, fd)
        self.assertEqual(result['decision'], 'detected')
        self.assertEqual(len(result['detections']), 1)

    def test_parent_timeout_kills_and_reaps_process(self):
        original_popen = subprocess.Popen
        processes = []

        def slow_child(command, **kwargs):
            process = original_popen([sys.executable, '-c', 'import time; time.sleep(30)'], **kwargs)
            processes.append(process)
            return process

        with execution_lock(self.lock) as fd, patch('assessments.isolation.subprocess.Popen', side_effect=slow_child):
            with self.assertRaises(ModelError) as caught:
                run_detection(self.snapshot(), self.image, self.root, self.media, 0.05, fd)
        self.assertEqual(caught.exception.code, 'INFERENCE_TIMEOUT')
        self.assertIsNotNone(processes[0].poll())
        with execution_lock(self.lock) as fd:
            self.assertIsNotNone(fd)

    def test_non_object_child_json_is_rejected_as_invalid_output(self):
        real_popen = subprocess.Popen
        for raw in ('[]', '42', 'null', '"unexpected"'):
            with self.subTest(raw=raw):
                def malformed_child(command, **kwargs):
                    return real_popen([sys.executable, '-c', 'import sys; sys.stdout.write(sys.argv[1])', raw], **kwargs)
                with execution_lock(self.lock) as fd, patch('assessments.isolation.subprocess.Popen', side_effect=malformed_child):
                    with self.assertRaises(ModelError) as caught:
                        run_detection(self.snapshot(), self.image, self.root, self.media, 10, fd)
                self.assertEqual(caught.exception.code, 'MODEL_OUTPUT_INVALID')


class DetectorRegistryTests(RuntimeFixture, TestCase):
    def test_registration_is_idempotent_and_independent_of_flower_model(self):
        flower = ModelVersion.objects.create(name='existing-flower', version='v1', enabled=True)
        model = register_detector(self.manifest, activate=True)
        self.assertEqual(register_detector(self.manifest).pk, model.pk)
        flower.refresh_from_db()
        self.assertTrue(flower.enabled)
        self.assertTrue(model.enabled)
        self.assertEqual(DetectionModel.objects.count(), 1)
        status = public_status()
        self.assertEqual(status['labels'], [{'id': 1, 'name': 'Synthetic debris'}])
        self.assertNotIn('artifact', status)
        self.assertEqual(snapshot_for(model)['config_digest'], model.config_digest)
        activate_detector(None)
        self.assertFalse(public_status()['enabled'])

    def test_changed_configuration_cannot_replace_registered_version(self):
        register_detector(self.manifest)
        self.manifest_data['threshold'] = 0.7
        self.write_manifest()
        with self.assertRaises(ModelError) as caught:
            register_detector(self.manifest)
        self.assertEqual(caught.exception.code, 'MODEL_VERSION_EXISTS')

    def test_activation_verifies_weight_and_health_disables_missing_file(self):
        model = register_detector(self.manifest, activate=True)
        self.artifact.unlink()
        self.assertFalse(public_status()['enabled'])
        with self.assertRaises(ModelError):
            activate_detector(model.pk)
