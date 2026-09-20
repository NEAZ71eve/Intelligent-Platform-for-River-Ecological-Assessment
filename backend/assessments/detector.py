"""Bounded CPU YOLOv8 execution, used only in the isolated worker child."""
from recognition.adapter import create_session, load_image, low_image_quality
from .artifacts import ModelError, verify_artifact

MAX_CANDIDATES = 30000
MAX_NMS_CANDIDATES = 3000
MAX_DETECTIONS = 100


def validate_graph(blob, class_count):
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
        input_tensor, output_tensor = model.graph.input[0].type.tensor_type, model.graph.output[0].type.tensor_type
        input_shape = [d.dim_value for d in input_tensor.shape.dim]
        output_shape = [d.dim_value for d in output_tensor.shape.dim]
        if input_tensor.elem_type != onnx.TensorProto.FLOAT or input_shape != [1, 3, 640, 640]:
            raise ModelError('MODEL_IO_INVALID')
        if output_tensor.elem_type != onnx.TensorProto.FLOAT or len(output_shape) != 3 or output_shape[:2] != [1, 4 + class_count] or not 1 <= output_shape[2] <= MAX_CANDIDATES:
            raise ModelError('MODEL_IO_INVALID')
        onnx.checker.check_model(model)
    except ModelError:
        raise
    except Exception as exc:
        raise ModelError('MODEL_FORMAT_INVALID') from exc


def validate_output(raw, class_count):
    import numpy as np
    if not isinstance(raw, np.ndarray) or raw.dtype != np.float32 or raw.ndim != 3 or raw.shape[:2] != (1, 4 + class_count) or not 1 <= raw.shape[2] <= MAX_CANDIDATES or not np.isfinite(raw).all():
        raise ModelError('MODEL_OUTPUT_INVALID')
    if np.any(raw[:, 4:] < 0) or np.any(raw[:, 4:] > 1):
        raise ModelError('MODEL_OUTPUT_INVALID')


def postprocess(raw, labels, supported_class_ids, conf_thres=0.5, iou_thres=0.45):
    """Select only supported winning heads, filter bad boxes and bound greedy NMS."""
    import numpy as np
    validate_output(raw, len(labels))
    prediction = raw[0].T
    classes = prediction[:, 4:].argmax(axis=1)
    confidence = prediction[:, 4:].max(axis=1)
    keep = (confidence >= conf_thres) & np.isin(classes, supported_class_ids) & (prediction[:, 2] > 0) & (prediction[:, 3] > 0)
    prediction, classes, confidence = prediction[keep], classes[keep], confidence[keep]
    order = np.argsort(-confidence, kind='stable')[:MAX_NMS_CANDIDATES]
    prediction, classes, confidence = prediction[order], classes[order], confidence[order]
    # Float64 avoids overflow when malformed finite float32 coordinates are huge.
    centers, sizes = prediction[:, :2].astype(np.float64), prediction[:, 2:4].astype(np.float64)
    xy = np.concatenate((centers - sizes / 2, centers + sizes / 2), axis=1)
    out, suppressed = [], np.zeros(len(confidence), dtype=bool)
    for i in range(len(confidence)):
        if suppressed[i]:
            continue
        out.append({'class_id': int(classes[i]), 'confidence': float(confidence[i]), 'bbox': xy[i].tolist()})
        if len(out) >= MAX_DETECTIONS:
            break
        intersection = np.clip(np.minimum(xy[i, 2:], xy[:, 2:]) - np.maximum(xy[i, :2], xy[:, :2]), 0, None).prod(axis=1)
        union = sizes[i].prod() + sizes.prod(axis=1) - intersection
        iou = np.divide(intersection, union, out=np.zeros_like(intersection), where=union > 0)
        suppressed |= (iou > iou_thres) & (classes == classes[i])
    return out


def preprocess(image):
    import numpy as np
    from PIL import Image
    width, height = image.size
    scale = min(640 / width, 640 / height)
    new_width, new_height = max(1, round(width * scale)), max(1, round(height * scale))
    pad_x, pad_y = (640 - new_width) // 2, (640 - new_height) // 2
    padded = Image.new('RGB', (640, 640), (114, 114, 114))
    padded.paste(image.resize((new_width, new_height), Image.Resampling.BILINEAR), (pad_x, pad_y))
    pixels = np.asarray(padded, dtype=np.float32) / np.float32(255)
    return np.ascontiguousarray(pixels.transpose(2, 0, 1)[None]), (new_width / width, new_height / height, pad_x, pad_y)


def _run(session, pixels):
    try:
        return session.run(None, {session.get_inputs()[0].name: pixels})[0]
    except Exception as exc:
        raise ModelError('MODEL_INFERENCE_FAILED') from exc


def validate_model(snapshot, model_root):
    import numpy as np
    blob = verify_artifact(model_root, snapshot, return_bytes=True)
    validate_graph(blob, len(snapshot['labels']))
    validate_output(_run(create_session(blob), np.zeros((1, 3, 640, 640), dtype=np.float32)), len(snapshot['labels']))


def infer(snapshot, image_path, model_root, media_root):
    blob = verify_artifact(model_root, snapshot, return_bytes=True)
    validate_graph(blob, len(snapshot['labels']))
    image = load_image(image_path, media_root)
    result = {'detections': [], 'image_width': image.width, 'image_height': image.height,
              'decision': 'uncertain', 'reason': 'NO_SUPPORTED_DETECTIONS'}
    if low_image_quality(image):
        result['reason'] = 'LOW_IMAGE_QUALITY'
        return result
    pixels, (scale_x, scale_y, pad_x, pad_y) = preprocess(image)
    boxes = postprocess(_run(create_session(blob), pixels), snapshot['labels'],
                        snapshot['preprocessing']['supported_class_ids'], snapshot['threshold'])
    for box in boxes:
        x1, y1, x2, y2 = box['bbox']
        x1, x2 = [min(image.width, max(0, (x - pad_x) / scale_x)) for x in (x1, x2)]
        y1, y2 = [min(image.height, max(0, (y - pad_y) / scale_y)) for y in (y1, y2)]
        if x2 <= x1 or y2 <= y1:
            continue
        label = snapshot['labels'][box['class_id']]
        result['detections'].append({
            **box, 'label': label['name'], 'eval_category': label['eval_category'],
            'bbox': [x1, y1, x2, y2],
            'area_ratio': round((x2 - x1) * (y2 - y1) / (image.width * image.height), 6),
        })
    if result['detections']:
        result.update(decision='detected', reason='')
    return result
