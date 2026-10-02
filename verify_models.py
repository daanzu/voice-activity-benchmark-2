"""Verify the two exact ONNX artifacts used in the historical experiment."""
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPECTED = {
    'packages/silero_vad_lite/data/silero_vad.onnx': '2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f',
    'silero_current.onnx': '1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3',
}

if __name__ == '__main__':
    for relative, expected in EXPECTED.items():
        path = ROOT / relative
        actual = sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(f'Model hash mismatch: {relative}: {actual}')
        print(f'OK {relative} {actual}')
