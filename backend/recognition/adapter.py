"""CPU inference implementation. Imported only by the isolated child and tests."""
import io
from pathlib import Path

from .artifacts import ModelError, verify_artifact

DISCLAIMER = '分数是模型排序分数，不是准确率；仅支持登记的五类花卉，尚未验证开放集识别，不能用于安全或专业判断。'


def validate_graph(blob):
    import onnx
    try:
        model = onnx.load_model_from_string(blob)
        def visit(message):
            if isinstance(message, onnx.TensorProto) and (message.data_location == onnx.TensorProto.EXTERNAL or message.external_data):
                raise ModelError('MODEL_EXTERNAL_DATA_FORBIDDEN')
            if isinstance(message, onnx.NodeProto) and message.domain not in ('', 'ai.onnx'):
                raise ModelError('MODEL_CUSTOM_OP_FORBIDDEN')
            for field, value in message.ListFields():
                if field.type == field.TYPE_MESSAGE:
                    if field.is_repeated:
                        for item in value:
                            visit(item)
                    else:
                        visit(value)
        visit(model)
        if model.functions or len(model.graph.input) != 1 or len(model.graph.output) != 1:
            raise ModelError('MODEL_IO_INVALID')
        for info, expected in [(model.graph.input[0], [3, 224, 224]), (model.graph.output[0], [5])]:
            tensor = info.type.tensor_type
            dims = tensor.shape.dim
            if tensor.elem_type != onnx.TensorProto.FLOAT or len(dims) != len(expected) + 1:
                raise ModelError('MODEL_IO_INVALID')
            if dims[0].HasField('dim_value') and dims[0].dim_value != 1:
                raise ModelError('MODEL_IO_INVALID')
            if [dim.dim_value for dim in dims[1:]] != expected:
                raise ModelError('MODEL_IO_INVALID')
        onnx.checker.check_model(model)
    except ModelError:
        raise
    except Exception as exc:
        raise ModelError('MODEL_FORMAT_INVALID') from exc


def load_image(path, media_root):
    from PIL import Image, ImageOps
    try:
        resolved = Path(path).resolve(strict=True)
        if not resolved.is_relative_to(Path(media_root).resolve(strict=True)) or not resolved.is_file():
            raise ModelError('IMAGE_PATH_INVALID')
        with resolved.open('rb') as stream:
            raw = stream.read(6 * 1024 * 1024 + 1)
        if len(raw) > 6 * 1024 * 1024:
            raise ModelError('INVALID_IMAGE')
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in ('JPEG', 'PNG', 'WEBP') or getattr(source, 'is_animated', False) or source.width * source.height > 2048 * 2048:
                raise ModelError('INVALID_IMAGE')
            return ImageOps.exif_transpose(source).convert('RGB')
    except ModelError:
        raise
    except Exception as exc:
        raise ModelError('IMAGE_UNAVAILABLE') from exc


def low_image_quality(image):
    from PIL import ImageStat
    if min(image.size) < 32:
        return True
    reduced = image.copy()
    reduced.thumbnail((128, 128))
    # Channel-wise spatial variation also catches a perfectly red/green image.
    return max(ImageStat.Stat(reduced).stddev) < 2.0


def preprocess(image, config):
    import numpy as np
    from PIL import Image
    width, height = image.size
    shorter = config['resize_shorter']
    resized = (shorter, int(height * shorter / width)) if width <= height else (int(width * shorter / height), shorter)
    image = image.resize(resized, Image.Resampling.BILINEAR)
    crop = config['crop_size']
    left, top = int(round((image.width - crop) / 2.0)), int(round((image.height - crop) / 2.0))
    image = image.crop((left, top, left + crop, top + crop))
    pixels = np.asarray(image, dtype=np.float32) / np.float32(255.0)
    pixels = (pixels - np.asarray(config['mean'], dtype=np.float32)) / np.asarray(config['std'], dtype=np.float32)
    return np.ascontiguousarray(pixels.transpose(2, 0, 1)[None, ...], dtype=np.float32)


def create_session(blob):
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.add_session_config_entry('session.intra_op.allow_spinning', '0')
    options.add_session_config_entry('session.inter_op.allow_spinning', '0')
    options.log_severity_level = 3
    try:
        # Passing verified bytes prevents a path replacement between hash and load.
        return ort.InferenceSession(blob, sess_options=options, providers=['CPUExecutionProvider'])
    except Exception as exc:
        raise ModelError('MODEL_RUNTIME_INVALID') from exc


def validate_model(snapshot, model_root):
    import numpy as np
    blob = verify_artifact(model_root, snapshot, return_bytes=True)
    validate_graph(blob)
    session = create_session(blob)
    try:
        output = session.run(None, {session.get_inputs()[0].name: np.zeros((1, 3, 224, 224), dtype=np.float32)})[0]
    except Exception as exc:
        raise ModelError('MODEL_RUNTIME_INVALID') from exc
    if output.shape != (1, 5) or output.dtype != np.float32 or not np.isfinite(output).all():
        raise ModelError('MODEL_OUTPUT_INVALID')


def infer(snapshot, image_path, model_root, media_root):
    import numpy as np
    blob = verify_artifact(model_root, snapshot, return_bytes=True)
    validate_graph(blob)
    result = {
        'decision': 'uncertain', 'candidates': [], 'threshold': snapshot['threshold'],
        'model': {key: snapshot[key] for key in ('id', 'name', 'version', 'checksum', 'config_digest')},
        'scope': snapshot['scope'], 'disclaimer': DISCLAIMER,
    }
    image = load_image(image_path, media_root)
    if low_image_quality(image):
        result['reason'] = 'LOW_IMAGE_QUALITY'
        return result
    session = create_session(blob)
    try:
        output = session.run(None, {session.get_inputs()[0].name: preprocess(image, snapshot['preprocessing'])})[0]
    except Exception as exc:
        raise ModelError('MODEL_INFERENCE_FAILED') from exc
    if output.shape != (1, 5) or output.dtype != np.float32 or not np.isfinite(output).all():
        raise ModelError('MODEL_OUTPUT_INVALID')
    values = output[0].astype(np.float64)
    probabilities = np.exp(values - values.max())
    probabilities /= probabilities.sum()
    for index in np.argsort(-probabilities, kind='stable')[:3]:
        label = snapshot['labels'][int(index)]
        result['candidates'].append({'label': label['id'], 'name': label['name'], 'score': float(probabilities[index]), 'content_id': None})
    if result['candidates'][0]['score'] >= snapshot['threshold']:
        result['decision'] = 'recognized'
    else:
        result['reason'] = 'LOW_CONFIDENCE'
    return result
