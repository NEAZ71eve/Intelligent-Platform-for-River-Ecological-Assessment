import pytest
from training.audit_datasets import audit_image_dir

def test_audit_returns_per_source_stats(tmp_path):
    img = tmp_path / "img1.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 100)
    stats = audit_image_dir(tmp_path)
    assert stats["total_images"] == 1
    assert stats["total_bytes"] == 104

def test_audit_dedup_by_dhash(tmp_path):
    data = b"\xff\xd8\xff\xe0" + b"0" * 100
    (tmp_path / "a.jpg").write_bytes(data)
    (tmp_path / "b.jpg").write_bytes(data)
    stats = audit_image_dir(tmp_path, dedup=True)
    assert stats["unique_images"] == 1
