#!/usr/bin/env python3
"""Fetch one pinned ONNX artifact, verify its hash, and copy the derived manifest."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request

COMMIT = 'c80982473418502fbff28f5864dbad8b97441ded'
ARTIFACT = 'river-eco-yolov8n-v1.onnx'
SHA256 = '96fc7178c28f1eb29bae9703f440d6bda9c041433edb3e335691f38a5ee6da6c'
URL = f'https://raw.githubusercontent.com/NEAZ71eve/Intelligent-Platform-for-River-Ecological-Assessment/{COMMIT}/inference/artifacts/{ARTIFACT}'
MAX_BYTES = 128 * 1024 * 1024


def fetch(destination):
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(__file__).with_name('river-floating-debris-v1.manifest.json')
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest['sha256'] != SHA256 or manifest['artifact'] != ARTIFACT:
        raise ValueError('Local manifest does not match pinned artifact')
    artifact = destination / ARTIFACT
    if not artifact.is_file() or hashlib.sha256(artifact.read_bytes()).hexdigest() != SHA256:
        temporary = None
        try:
            digest, size = hashlib.sha256(), 0
            with tempfile.NamedTemporaryFile(dir=destination, prefix='.river-download-', delete=False) as output:
                temporary = Path(output.name)
                with urllib.request.urlopen(URL, timeout=60) as response:
                    while block := response.read(1024 * 1024):
                        size += len(block)
                        if size > MAX_BYTES:
                            raise ValueError('Artifact exceeds size limit')
                        digest.update(block)
                        output.write(block)
            if not size or digest.hexdigest() != SHA256:
                raise ValueError('Artifact checksum mismatch')
            os.replace(temporary, artifact)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    copied_manifest = destination / manifest_path.name
    copied_manifest.write_bytes(manifest_bytes)
    print(f'Verified {artifact.name}: {SHA256}')
    print(f'Manifest: {copied_manifest}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, default=Path(__file__).resolve().parents[1] / 'artifacts')
    fetch(parser.parse_args().destination)
