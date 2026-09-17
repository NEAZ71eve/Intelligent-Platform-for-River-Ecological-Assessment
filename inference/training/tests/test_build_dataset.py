import pytest
from training.build_dataset import convert_voc_annotation, split_records

def test_voc_to_yolo_conversion(tmp_path):
    voc = tmp_path / "a.xml"
    voc.write_text("""<annotation><size><width>640</width><height>480</height></size>
    <object><name>bottle</name><bndbox>
    <xmin>10</xmin><ymin>20</ymin><xmax>50</xmax><ymax>100</ymax>
    </bndbox></object></annotation>""")
    out = convert_voc_annotation(voc)
    # YOLO: cx cy w h（归一化）
    assert out == [("bottle", 0.046875, 0.125, 0.0625, 0.16666666666666666)]

def test_split_frozen_and_disjoint():
    recs = [f"img{i}" for i in range(100)]
    tr, va, te = split_records(recs, seed=42)
    assert len(tr) + len(va) + len(te) == 100
    assert not (set(tr) & set(va) & set(te))
    tr2, _, _ = split_records([f"img{i}" for i in range(100)], seed=42)
    assert tr == tr2  # 固定种子可重放
