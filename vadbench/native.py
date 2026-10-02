"""Frame-by-frame ctypes adapters. No backend libraries are bundled.

Inputs are normalized float32 mono. Native PCM scaling is performed here, never
by callers. Unknown score alignment is explicit rather than silently compensated.
"""
from __future__ import annotations
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PINS = {
    'rnnoise': '70f1d256acd4b34a572f999a05c87bf00b67730d',
    'speex': '1b28a0f61bc31162979e1f26f3981fc3637095c8',
    'agc2': '10209d27953cad3affadfdcca968c0066cea0830',
    'ten': '22a3bcd4509d0faaa8eef4881e8af5f39c178950',
}
FP = C.POINTER(C.c_float)
IP = C.POINTER(C.c_int16)


def _frame(frame, n):
    x = np.asarray(frame, dtype=np.float32)
    if x.shape != (n,) or not np.isfinite(x).all() or np.any(np.abs(x) > 1):
        raise ValueError(f'Expected {n} finite normalized mono samples in [-1, 1]')
    return np.ascontiguousarray(x)


def _pcm16(x):
    return np.clip(np.rint(x * 32768.0), -32768, 32767).astype(np.int16)


class _Native:
    def _load(self, key, filename, path, source, license_name):
        path = Path(path or os.environ.get(f'VADBENCH_{key.upper()}_LIB', ROOT / '.deps' / filename))
        if not path.is_file():
            raise FileNotFoundError(f'{key}: missing {path}; see docs/NATIVE_BACKENDS.md')
        self.lib = C.CDLL(str(path.resolve()))
        self._state = None
        self.metadata = dict(name=key, backend=key, score_kind='probability', source=source, source_pin=PINS[key],
            library_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            license=license_name, sample_rate=self.sample_rate, frame_samples=self.frame_samples,
            score_delay_s=None, lookahead_s=None,
            alignment='Uncalibrated native streaming score; no timestamp compensation',
            input_scaling='normalized float32 converted to native PCM scale')
        manifest_path = ROOT / '.deps/native-manifest.json'
        self.metadata['reference_source_pin'] = PINS[key]
        verified = False
        if manifest_path.is_file() and key != 'ten':
            try:
                manifest = json.loads(manifest_path.read_text())
                verified = manifest.get('libraries', {}).get(filename) == self.metadata['library_sha256']
            except (ValueError, OSError):
                pass
        self.metadata['matches_local_build_manifest'] = verified
        if not verified:
            self.metadata['source_pin'] = None


    def close(self):
        if getattr(self, '_state', None):
            self._destroy()
            self._state = None

    def __del__(self):
        self.close()

    def reset(self):
        self.close()
        self._create()
        if not self._state:
            raise RuntimeError('Native VAD allocation failed')


class RNNoiseAdapter(_Native):
    """Pinned current RNNoise full denoising pipeline's returned VAD probability."""
    sample_rate, frame_samples = 48000, 480
    def __init__(self, path=None):
        self._load('rnnoise', 'librnnoise.so', path, 'https://github.com/xiph/rnnoise', 'BSD-3-Clause')
        self.lib.rnnoise_create.argtypes = [C.c_void_p]
        self.lib.rnnoise_create.restype = C.c_void_p
        self.lib.rnnoise_destroy.argtypes = [C.c_void_p]
        self.lib.rnnoise_process_frame.argtypes = [C.c_void_p, FP, FP]
        self.lib.rnnoise_process_frame.restype = C.c_float
        self.lib.rnnoise_get_frame_size.restype = C.c_int
        if self.lib.rnnoise_get_frame_size() != self.frame_samples:
            raise RuntimeError('Unexpected RNNoise frame size')
        self.metadata['version'] = '70f1d256 (current architecture, default full model)'
        self.metadata['model_archive_sha256'] = '0a8755f8e2d834eff6a54714ecc7d75f9932e845df35f8b59bc52a7cfe6e8b37'
        self.metadata['build'] = 'gcc -O3 -march=native; rebuild on the target CPU'
        self.metadata['processing'] = 'Full native denoising call; output audio discarded'
        self.reset()
    def _create(self): self._state = self.lib.rnnoise_create(None)
    def _destroy(self): self.lib.rnnoise_destroy(self._state)
    def process(self, frame):
        x = _frame(frame, self.frame_samples) * np.float32(32768)
        out = np.empty_like(x)
        return float(self.lib.rnnoise_process_frame(self._state, out.ctypes.data_as(FP), x.ctypes.data_as(FP)))


class SpeexAdapter(_Native):
    """SpeexDSP preprocessor probability (integer percent resolution)."""
    sample_rate, frame_samples = 16000, 320
    def __init__(self, path=None):
        self._load('speex', 'libspeexdsp.so', path, 'https://github.com/xiph/speexdsp', 'BSD-3-Clause')
        self.lib.speex_preprocess_state_init.argtypes = [C.c_int, C.c_int]
        self.lib.speex_preprocess_state_init.restype = C.c_void_p
        self.lib.speex_preprocess_state_destroy.argtypes = [C.c_void_p]
        self.lib.speex_preprocess_run.argtypes = [C.c_void_p, IP]
        self.lib.speex_preprocess_ctl.argtypes = [C.c_void_p, C.c_int, C.c_void_p]
        self.metadata.update(lookahead_s=0.0, version='1.2.1', score_resolution=0.01,
            processing='Preprocessor; VAD enabled, denoise enabled, AGC disabled')
        self.reset()
    def _ctl(self, code, value):
        v = C.c_int(value)
        if self.lib.speex_preprocess_ctl(self._state, code, C.byref(v)) != 0:
            raise RuntimeError(f'Speex control failed: {code}')
        return v.value
    def _create(self):
        self._state = self.lib.speex_preprocess_state_init(self.frame_samples, self.sample_rate)
        if self._state:
            self._ctl(4, 1)
            self._ctl(0, 1)
            self._ctl(2, 0)
    def _destroy(self): self.lib.speex_preprocess_state_destroy(self._state)
    def process(self, frame):
        x = _pcm16(_frame(frame, self.frame_samples))
        self.lib.speex_preprocess_run(self._state, x.ctypes.data_as(IP))
        return self._ctl(45, 0) / 100.0


class Agc2Adapter(_Native):
    """Historical WebRTC AGC2 RNN VAD extraction, explicitly not full APM."""
    sample_rate, frame_samples = 24000, 240
    def __init__(self, path=None):
        self._load('agc2', 'libagc2vad.so', path, 'https://github.com/daanzu/webrtc_rnnvad',
                   'WebRTC BSD-3-Clause; bundled third-party notices apply')
        self.lib.vadbench_agc2_create.restype = C.c_void_p
        self.lib.vadbench_agc2_destroy.argtypes = [C.c_void_p]
        self.lib.vadbench_agc2_process.argtypes = [C.c_void_p, FP]
        self.lib.vadbench_agc2_process.restype = C.c_float
        self.metadata['lookahead_s'] = 0.0
        self.metadata['implementation'] = 'Historical third-party extraction of WebRTC AGC2 RNN; not current upstream APM'
        self.reset()
    def _create(self): self._state = self.lib.vadbench_agc2_create()
    def _destroy(self): self.lib.vadbench_agc2_destroy(self._state)
    def process(self, frame):
        x = _frame(frame, self.frame_samples) * np.float32(32768)
        return float(self.lib.vadbench_agc2_process(self._state, x.ctypes.data_as(FP)))


class TenAdapter(_Native):
    """User-supplied TEN native library. Never obtains or accepts its license."""
    sample_rate, frame_samples = 16000, 256
    def __init__(self, path=None):
        path = path or os.environ.get('VADBENCH_TEN_LIB')
        if not path:
            raise FileNotFoundError('TEN requires a separately obtained library after license review; set VADBENCH_TEN_LIB')
        self._load('ten', '', path, 'https://github.com/TEN-framework/ten-vad',
                   'Apache-2.0 with additional noncompetition/use restrictions; see upstream LICENSE')
        self.lib.ten_vad_create.argtypes = [C.POINTER(C.c_void_p), C.c_size_t, C.c_float]
        self.lib.ten_vad_destroy.argtypes = [C.POINTER(C.c_void_p)]
        self.lib.ten_vad_process.argtypes = [C.c_void_p, IP, C.c_size_t, FP, C.POINTER(C.c_int)]
        self.lib.ten_vad_get_version.restype = C.c_char_p
        self.metadata['version'] = self.lib.ten_vad_get_version().decode()
        self.metadata['source_pin'] = None
        self.metadata['api_reference_pin'] = PINS['ten']
        self.metadata['reference_source_declared_lookahead_s'] = 0.016
        if self.metadata['library_sha256'] == '5abfe6bf6e9a4fcea6b440240f0a9a0f431ab5006e48a4e16465ebe681ffd90f':
            self.metadata['lookahead_s'] = 0.016
            self.metadata['binary_repository_pin'] = PINS['ten']
        self.metadata['provenance'] = 'Externally supplied library; hash recorded, source correspondence unverified'
        self.reset()
    def _create(self):
        self._state = C.c_void_p()
        if self.lib.ten_vad_create(C.byref(self._state), self.frame_samples, C.c_float(0.5)) != 0:
            raise RuntimeError('TEN create failed')
    def _destroy(self):
        if self.lib.ten_vad_destroy(C.byref(self._state)) != 0:
            raise RuntimeError('TEN destroy failed')
    def process(self, frame):
        x = _pcm16(_frame(frame, self.frame_samples))
        prob, flag = C.c_float(), C.c_int()
        if self.lib.ten_vad_process(self._state, x.ctypes.data_as(IP), self.frame_samples, C.byref(prob), C.byref(flag)) != 0:
            raise RuntimeError('TEN process failed')
        return float(prob.value)
