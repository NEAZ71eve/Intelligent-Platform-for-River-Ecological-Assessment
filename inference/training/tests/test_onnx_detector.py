import numpy as np
import pytest
from training.onnx_detector import postprocess

def _fake_output(nc=16, boxes=8400):
    # YOLOv8 ONNX 输出: (1, 4+nc, boxes)
    raw = np.zeros((1, 4 + nc, boxes), dtype=np.float32)
    raw[0, 0, 0] = 10; raw[0, 1, 0] = 10   # cx cy
    raw[0, 2, 0] = 20; raw[0, 3, 0] = 20   # w h
    raw[0, 4 + 0, 0] = 0.9                  # class0 conf
    raw[0, 4 + 5, 1] = 0.8                  # class5 conf
    return raw

def test_postprocess_nms_and_conf():
    dets = postprocess(_fake_output(), conf_thres=0.5, iou_thres=0.45)
    assert len(dets) == 2
    d0 = dets[0]
    assert set(d0) == {"class_id", "conf", "x1", "y1", "x2", "y2"}
    assert d0["class_id"] == 0 and d0["conf"] == pytest.approx(0.9)

def test_low_conf_filtered():
    raw = _fake_output(); raw[0, 4 + 0, 0] = 0.3
    dets = postprocess(raw, conf_thres=0.5, iou_thres=0.45)
    # box0 conf 0.3 被过滤，仅剩 class5 框
    assert all(d["class_id"] != 0 or d["conf"] > 0.4 for d in dets)

def test_empty_output_returns_empty():
    raw = np.zeros((1, 4 + 16, 100), dtype=np.float32)  # 全 0，无框过阈值
    assert postprocess(raw, conf_thres=0.5) == []
