"""Verify licensed source, remove exact duplicates, group near duplicates, freeze splits."""
import argparse
import collections
import hashlib
import json
import random
import shutil
import tarfile
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[2]
SOURCE_URL = "https://storage.googleapis.com/download.tensorflow.org/example_images/flower_photos.tgz"
ARCHIVE_SHA256 = "4c54ace7911aaffe13a365c34f650e71dd5bf1be0a58b464e5a7183e3e595d9c"
SEED = 20260916
LABELS = [
    {"id": "daisy", "name": "雏菊类花卉", "knowledge_slug": "flower-daisy"},
    {"id": "dandelion", "name": "蒲公英类花卉", "knowledge_slug": "flower-dandelion"},
    {"id": "roses", "name": "蔷薇属花卉", "knowledge_slug": "flower-roses"},
    {"id": "sunflowers", "name": "向日葵类花卉", "knowledge_slug": "flower-sunflowers"},
    {"id": "tulips", "name": "郁金香类花卉", "knowledge_slug": "flower-tulips"},
]


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def dhash(image):
    gray = ImageOps.exif_transpose(image).convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    values = list(gray.getdata())
    result = 0
    for y in range(8):
        for x in range(8):
            result = (result << 1) | (values[y * 9 + x] > values[y * 9 + x + 1])
    return result


def prepare(archive, output):
    if sha256(archive) != ARCHIVE_SHA256:
        raise ValueError("Official archive differs from the pinned SHA256; do not silently change the experiment.")
    dataset_parent = ROOT / ".runtime/datasets"
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        if sum(m.size for m in members) > 1024**3:
            raise ValueError("Unexpected archive expansion size")
        for member in members:
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts or path.parts[0] != "flower_photos" or not (member.isfile() or member.isdir()):
                raise ValueError("Unexpected archive member")
        tar.extractall(dataset_parent, filter="data")
    dataset = dataset_parent / "flower_photos"
    license_text = (dataset / "LICENSE.txt").read_text(encoding="utf-8")
    if "https://creativecommons.org/licenses/by/2.0/" not in license_text:
        raise ValueError("Expected CC-BY-2.0 license declaration missing")
    attributions = {line.split(" CC-BY", 1)[0]: line for line in license_text.splitlines() if " CC-BY" in line}
    images, excluded, seen = [], [], {}
    for class_index, label in enumerate(LABELS):
        for path in sorted((dataset / label["id"]).glob("*.jpg")):
            relative = path.relative_to(dataset).as_posix()
            if relative not in attributions:
                raise ValueError(f"Missing per-image credit: {relative}")
            digest = sha256(path)
            if digest in seen:
                excluded.append({"path": relative, "reason": "exact_sha256_duplicate", "duplicate_of": seen[digest]})
                continue
            with Image.open(path) as image:
                image.load()
                perceptual = dhash(image)
                width, height = image.size
            images.append({"path": relative, "class_index": class_index, "sha256": digest, "dhash": f"{perceptual:016x}", "width": width, "height": height})
            seen[digest] = relative
    if len(images) + len(excluded) != 3670:
        raise ValueError("Unexpected dataset image count")

    parent = list(range(len(images)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    near_pairs = []
    hashes = [int(row["dhash"], 16) for row in images]
    # 6.7 million cheap 64-bit comparisons for this small dataset; no extra dependency.
    for i, left in enumerate(hashes):
        for j in range(i):
            distance = (left ^ hashes[j]).bit_count()
            if distance <= 4:
                parent[find(i)] = find(j)
                near_pairs.append({"left": images[j]["path"], "right": images[i]["path"], "distance": distance})
    groups = collections.defaultdict(list)
    for index, image in enumerate(images):
        groups[find(index)].append(image)
    valid_groups = []
    for group in groups.values():
        group_id = min(item["sha256"] for item in group)[:24]
        if len({item["class_index"] for item in group}) > 1:
            excluded.extend({"path": item["path"], "reason": "cross_label_near_duplicate_group", "group": group_id} for item in group)
            continue
        for item in group:
            item["group"] = group_id
        valid_groups.append(group)

    # Greedy per-class allocation: every perceptual group is indivisible across splits.
    rng = random.Random(SEED)
    counts = {}
    assigned = []
    for class_index, label in enumerate(LABELS):
        class_groups = [g for g in valid_groups if g[0]["class_index"] == class_index]
        rng.shuffle(class_groups)
        class_groups.sort(key=len, reverse=True)
        total = sum(map(len, class_groups))
        targets = {"train": total * .70, "validation": total * .15, "test": total * .15}
        current = {name: 0 for name in targets}
        for group in class_groups:
            split = max(targets, key=lambda name: targets[name] - current[name])
            for item in group:
                item["split"] = split
                assigned.append(item)
            current[split] += len(group)
        counts[label["id"]] = current
    assigned.sort(key=lambda row: row["path"])
    group_splits = collections.defaultdict(set)
    for row in assigned:
        group_splits[row["group"]].add(row["split"])
    assert all(len(splits) == 1 for splits in group_splits.values())
    manifest = {
        "schema_version": 1, "dataset": "tensorflow-flower-photos", "source_url": SOURCE_URL,
        "archive_sha256": ARCHIVE_SHA256, "license": "CC-BY-2.0", "attribution_file": "FLOWER_PHOTOS_ATTRIBUTION.txt",
        "seed": SEED, "split_ratio": {"train": .70, "validation": .15, "test": .15},
        "deduplication": {"exact": "SHA256 retain first sorted image", "perceptual": "64-bit dHash <= 4, connected-component group split", "near_pairs": near_pairs},
        "labels": LABELS, "counts": counts, "excluded": excluded, "images": assigned,
        "limitations": ["Five flower image categories only; not species-level botanical identification.", "No campus-shot dataset or open-set/non-target evaluation available.", "Perceptual hashing is a leakage precaution, not proof that all semantically similar images were found."],
    }
    if output.exists():
        old = json.loads(output.read_text())
        if old != manifest:
            raise ValueError("Frozen split differs; create an explicit new experiment version instead of replacing it")
    else:
        write_json(output, manifest)
    shutil.copyfile(dataset / "LICENSE.txt", output.parent / "FLOWER_PHOTOS_ATTRIBUTION.txt")
    summary = {"archive_sha256": ARCHIVE_SHA256, "split_sha256": sha256(output), "images_raw": 3670, "images_used": len(assigned), "excluded_count": len(excluded), "near_pair_count": len(near_pairs), "group_count": len(group_splits), "counts": counts, "cross_split_group_overlap": 0}
    write_json(ROOT / "inference/reports/data_audit_v1.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=ROOT / ".runtime/datasets/flower_photos.tgz")
    parser.add_argument("--output", type=Path, default=ROOT / "inference/data/flowers_split_v1.json")
    args = parser.parse_args()
    prepare(args.archive, args.output)
