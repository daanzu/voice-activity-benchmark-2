#!/usr/bin/env python3
"""Fetch checksum-pinned official FSMN artifacts and minimal CPU inference packages."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vadbench.fsmn import HASHES, REVISION
DEST = ROOT / '.deps/fsmn'

def main():
    DEST.mkdir(parents=True, exist_ok=True)
    for name, digest in HASHES.items():
        path = DEST / name
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            url = f'https://huggingface.co/funasr/fsmn-vad-onnx/resolve/{REVISION}/{name}'
            data = urllib.request.urlopen(url).read()
            if hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError(f'Checksum mismatch: {name}')
            path.write_bytes(data)
    # Pins are portable; pip resolves official PyPI wheels for the local platform.
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', '--report', str(DEST / 'pip-install-report.json'),
                    '--target', str(DEST / 'packages'),
                    'kaldi-native-fbank==1.22.3', 'onnxruntime==1.19.2', 'numpy==1.26.4'], check=True)
    manifest = {'repository': 'https://huggingface.co/funasr/fsmn-vad-onnx',
                'revision': REVISION, 'sha256': HASHES, 'license': 'Apache-2.0',
                'runtime': 'onnxruntime==1.19.2 (MIT)',
                'frontend': 'kaldi-native-fbank==1.22.3 (Apache-2.0)'}
    (DEST / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))

if __name__ == '__main__':
    main()
