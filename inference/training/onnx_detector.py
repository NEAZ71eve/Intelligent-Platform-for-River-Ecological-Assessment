"""YOLOv8 ONNX 输出后处理：转置、置信过滤、逐类 NMS，输出像素坐标框。

输入 raw 形状 (1, 4+nc, boxes) — YOLOv8 检测头原始输出。
输出 list[dict]，每个 dict: {class_id, conf, x1, y1, x2, y2}（像素坐标）。

注：本模块在 inference/ 训练侧维护；后端运行时按 HYHQ"生产环境只依赖 CPU 推理"
的约束，将本文件复制到 backend 内部模块（来源注释指向本原件），保持后处理单源。
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
    # cxcywh → xyxy
    xy = np.stack([boxes_wh[:, 0] - boxes_wh[:, 2] / 2,
                   boxes_wh[:, 1] - boxes_wh[:, 3] / 2,
                   boxes_wh[:, 0] + boxes_wh[:, 2] / 2,
                   boxes_wh[:, 1] + boxes_wh[:, 3] / 2], axis=1)
    # 逐类 NMS（贪心，按置信降序）
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
