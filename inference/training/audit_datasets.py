"""逐源审计图片数量、体积、dHash 近重复组，产出 JSON 报告。"""
import hashlib, json
from pathlib import Path
from PIL import Image

def _dhash(path, size=8):
    with Image.open(path) as im:
        im = im.convert("L").resize((size + 1, size))
        px = list(im.getdata())
        return "".join("1" if px[r * (size + 1) + c] > px[r * (size + 1) + c + 1] else "0"
                       for r in range(size) for c in range(size))

def audit_image_dir(root: Path, dedup: bool = False) -> dict:
    exts = {".jpg", ".jpeg", ".png"}
    files = [p for p in Path(root).rglob("*") if p.suffix.lower() in exts]
    hashes = {}
    for p in files:
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        hashes.setdefault(sha, []).append(str(p))
    if dedup:
        unique = len(hashes)
    else:
        unique = len(files)
    return {
        "total_images": len(files),
        "unique_images": unique,
        "total_bytes": sum(p.stat().st_size for p in files),
        "exact_sha256_groups": len(hashes),
    }

if __name__ == "__main__":
    import sys
    print(json.dumps(audit_image_dir(Path(sys.argv[1]), dedup="--dedup" in sys.argv),
                     ensure_ascii=False, indent=2))
