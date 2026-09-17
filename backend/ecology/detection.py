"""YOLOv8 检测 ONNX 后处理（后端运行时副本）。

来源：inference/training/onnx_detector.py（保持后处理单源）。
复制原因：HYHQ 生产环境只依赖 CPU ONNX Runtime，且后端不应跨包引用 inference/
训练侧模块。原件修改时请同步本副本。

输入 raw 形状 (1, 4+nc, boxes) — YOLOv8 检测头原始输出。
输出 list[dict]，每个 dict: {class_id, conf, x1, y1, x2, y2}（像素坐标）。
"""
import numpy as np


def postprocess(raw: np.ndarray, conf_thres: float = 0.5,
                iou_thres: float = 0.45) -> list:
    """YOLOv8 ONNX 原始输出 → 检测框列表（经 conf 过滤 + 逐类 NMS）。"""
    pred = raw[0].T                          # (boxes, 4+nc)
    boxes_wh = pred[:, :4]                   # cx, cy, w, h（像素）
    scores = pred[:, 4:]                     # (boxes, nc)
    class_ids = scores.argmax(axis=1)
    confs = scores.max(axis=1)
    keep = confs > conf_thres
    boxes_wh = boxes_wh[keep]
    class_ids = class_ids[keep]
    confs = confs[keep]
    if len(confs) == 0:
        return []
    xy = np.stack([boxes_wh[:, 0] - boxes_wh[:, 2] / 2,
                   boxes_wh[:, 1] - boxes_wh[:, 3] / 2,
                   boxes_wh[:, 0] + boxes_wh[:, 2] / 2,
                   boxes_wh[:, 1] + boxes_wh[:, 3] / 2], axis=1)
    out = []
    order = np.argsort(-confs)
    suppressed = np.zeros(len(confs), dtype=bool)
    for i in order:
        if suppressed[i]:
            continue
        out.append({"class_id": int(class_ids[i]), "conf": float(confs[i]),
                    "x1": float(xy[i, 0]), "y1": float(xy[i, 1]),
                    "x2": float(xy[i, 2]), "y2": float(xy[i, 3])})
        x1 = np.maximum(xy[i, 0], xy[:, 0])
        y1 = np.maximum(xy[i, 1], xy[:, 1])
        x2 = np.minimum(xy[i, 2], xy[:, 2])
        y2 = np.minimum(xy[i, 3], xy[:, 3])
        inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
        iou = inter / ((xy[i, 2] - xy[i, 0]) * (xy[i, 3] - xy[i, 1])
                       + (xy[:, 2] - xy[:, 0]) * (xy[:, 3] - xy[:, 1])
                       - inter + 1e-9)
        same = class_ids == class_ids[i]
        suppressed |= (iou > iou_thres) & same
    return out


def create_session(blob, providers=None):
    """创建 ONNX Runtime 会话；与 recognition.adapter.create_session 风格一致。

    生产环境建议改为子进程隔离（参考 recognition/isolation.run_child）。
    开发期/测试期可在主进程运行；测试通过 patch 本函数注入 fake session。
    """
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    options.add_session_config_entry("session.inter_op.allow_spinning", "0")
    options.log_severity_level = 3
    try:
        return ort.InferenceSession(blob, sess_options=options,
                                    providers=providers or ["CPUExecutionProvider"])
    except Exception as exc:
        raise RuntimeError("MODEL_RUNTIME_INVALID") from exc


def detect(snapshot, image_path, model_root, media_root):
    """运行 YOLOv8 检测推理，返回 {boxes, image_width, image_height}。

    snapshot 必须含：artifact, sha256, labels (list of {id, name, eval_category}),
    preprocessing (resize_size=640 等), threshold。
    """
    import io
    from pathlib import Path
    from PIL import Image, ImageOps
    from recognition.artifacts import verify_artifact

    blob = verify_artifact(model_root, snapshot, return_bytes=True)
    # 加载图像（复用 recognition.adapter.load_image 的安全约束）
    resolved = Path(image_path).resolve(strict=True)
    media_root_resolved = Path(media_root).resolve(strict=True)
    if not resolved.is_relative_to(media_root_resolved) or not resolved.is_file():
        raise RuntimeError("IMAGE_PATH_INVALID")
    with resolved.open("rb") as stream:
        raw_bytes = stream.read(6 * 1024 * 1024 + 1)
    if len(raw_bytes) > 6 * 1024 * 1024:
        raise RuntimeError("INVALID_IMAGE")
    with Image.open(io.BytesIO(raw_bytes)) as source:
        if source.format not in ("JPEG", "PNG", "WEBP") or getattr(source, "is_animated", False):
            raise RuntimeError("INVALID_IMAGE")
        image = ImageOps.exif_transpose(source).convert("RGB")
    orig_w, orig_h = image.size

    # YOLOv8 默认输入 640x640，letterbox 等比缩放
    input_size = int(snapshot.get("preprocessing", {}).get("resize_size", 640))
    scale = min(input_size / orig_w, input_size / orig_h)
    new_w, new_h = int(orig_w * scale), int(orig_h * scale)
    padded = Image.new("RGB", (input_size, input_size), (114, 114, 114))
    padded.paste(image.resize((new_w, new_h), Image.Resampling.BILINEAR),
                 ((input_size - new_w) // 2, (input_size - new_h) // 2))
    pixels = np.asarray(padded, dtype=np.float32) / 255.0
    pixels = np.ascontiguousarray(pixels.transpose(2, 0, 1)[None, ...], dtype=np.float32)

    session = create_session(blob)
    raw = session.run(None, {session.get_inputs()[0].name: pixels})[0]
    boxes = postprocess(raw, conf_thres=float(snapshot.get("threshold", 0.5)))

    # 像素坐标从 letterbox 空间映射回原图空间
    pad_x = (input_size - new_w) // 2
    pad_y = (input_size - new_h) // 2
    out = []
    for b in boxes:
        x1 = (b["x1"] - pad_x) / scale
        y1 = (b["y1"] - pad_y) / scale
        x2 = (b["x2"] - pad_x) / scale
        y2 = (b["y2"] - pad_y) / scale
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(orig_w, x2), min(orig_h, y2)
        out.append({"class_id": b["class_id"], "conf": b["conf"],
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2})
    return {"boxes": out, "image_width": orig_w, "image_height": orig_h}
