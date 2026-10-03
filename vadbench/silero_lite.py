"""Published native Silero VAD Lite wheels, isolated by version and process.

This is the package's ctypes/native inference path, not a reimplementation via
the benchmark's Python ONNX Runtime. The package owns the recurrent state and
64-sample context; callers supply only the 512 fresh normalized samples.
"""
import ctypes
import hashlib
import importlib
import importlib.metadata
from pathlib import Path
import platform
import sys
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INSTALL_ROOT = ROOT / '.deps/silero-vad-lite'
BACKEND_VERSIONS = {f'silero-lite-{v}': v for v in ('0.3.0', '0.4.0')}
PACKAGE_REPOSITORY = 'https://github.com/daanzu/py-silero-vad-lite'
# Deliberately pin the wheel for the documented CPython 3.12/Linux x86-64 setup.
# Other ABIs must receive separately reviewed wheel hashes, never an sdist build.
RELEASES = {
    '0.3.0': {
        'wheel_filename': 'silero_vad_lite-0.3.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl',
        'wheel_url': 'https://files.pythonhosted.org/packages/7d/e8/a21424477f1a82a1b447feeb12b35c87b60f32b50cbd20a79b8c7843bf07/silero_vad_lite-0.3.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl',
        'wheel_sha256': 'da7798f61ea453b3880d7002d45ab8745a6850697c68ac71e880f81f4e42fe8a',
        'package_source_commit': '64837cae29c0a920a679f4883f3a186d37de1f86',
        'model_release': 'Silero VAD v5.1',
        'model_sha256': '2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f',
    },
    '0.4.0': {
        'wheel_filename': 'silero_vad_lite-0.4.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl',
        'wheel_url': 'https://files.pythonhosted.org/packages/a0/37/13e8fda09212751093793dd56297e06aee2835bf76eea7bced17ee00c505/silero_vad_lite-0.4.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl',
        'wheel_sha256': 'bc2e57848ea923aff771df720a3155f41c89696ca85014303398dcb881d1a287',
        'package_source_commit': '83b81e6a68f1cc7e44d91fdf87235f0a77194201',
        'model_release': 'Silero VAD v6.2.3 (v6.2 streaming weights)',
        'model_sha256': '1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3',
    },
}
LIBRARY_SHA256 = '0e65d68994ce43439ac1aecd564e3a6ba3f71135c4b77248440e1d3c123d9cf9'
_ACTIVE_INSTALL = None


def sha256_file(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require_supported_platform():
    if (platform.python_implementation() != 'CPython' or sys.version_info[:2] != (3, 12)
            or sys.platform != 'linux' or platform.machine() != 'x86_64'):
        raise RuntimeError('Pinned Silero Lite wheels require CPython 3.12 on Linux x86-64')


def release_spec(version):
    if version not in RELEASES:
        raise ValueError(f'Unpinned Silero VAD Lite version: {version}')
    return RELEASES[version]


def verify_installation(version, install_root=DEFAULT_INSTALL_ROOT, packages=None):
    """Verify wheel, installed code, native library, model and distribution version.

    File hashes come directly from the checksum-pinned wheel, not a mutable
    setup manifest. The wheel remains available to audit the installed payload.
    """
    spec = release_spec(version)
    directory = Path(install_root).resolve() / version
    packages = Path(packages) if packages is not None else directory / 'packages'
    wheel = directory / spec['wheel_filename']
    if not wheel.is_file() or not packages.is_dir():
        raise RuntimeError('Run python scripts/setup_silero_lite.py to install the pinned wheels')
    if sha256_file(wheel) != spec['wheel_sha256']:
        raise ValueError(f'Silero Lite {version} wheel integrity failure')
    installed_hashes = {}
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.infolist():
            # pip regenerates RECORD; every other original wheel file must match.
            if member.is_dir() or member.filename.endswith('.dist-info/RECORD'):
                continue
            target = packages / member.filename
            expected = hashlib.sha256(archive.read(member)).hexdigest()
            if not target.is_file() or sha256_file(target) != expected:
                raise ValueError(f'Silero Lite {version} installed artifact integrity failure: {member.filename}')
            installed_hashes[member.filename] = expected
    model = packages / 'silero_vad_lite/data/silero_vad.onnx'
    library = packages / 'silero_vad_lite/data/silero_vad_lite.so'
    if sha256_file(model) != spec['model_sha256']:
        raise ValueError(f'Silero Lite {version} unexpected bundled model')
    if sha256_file(library) != LIBRARY_SHA256:
        raise ValueError(f'Silero Lite {version} unexpected native library')
    distributions = [d for d in importlib.metadata.distributions(path=[str(packages)])
                     if d.metadata['Name'].replace('_', '-').lower() == 'silero-vad-lite']
    if len(distributions) != 1 or distributions[0].version != version:
        raise ValueError(f'Silero Lite {version} unexpected installed distribution version')
    return {
        'package_name': 'silero-vad-lite', 'package_version': version,
        **spec, 'package_repository': PACKAGE_REPOSITORY,
        'pypi_release_url': f'https://pypi.org/project/silero-vad-lite/{version}/',
        'model_source_url': f'{PACKAGE_REPOSITORY}/blob/{spec["package_source_commit"]}/src/silero_vad_lite/data/silero_vad.onnx',
        'model_bytes': model.stat().st_size,
        'model_version': spec['model_release'],
        'library_sha256': LIBRARY_SHA256,
        'native_library_sha256': LIBRARY_SHA256, 'native_library_bytes': library.stat().st_size,
        'wheel_bytes': wheel.stat().st_size,
        'installed_artifact_sha256': installed_hashes,
        'runtime': 'ONNX Runtime 1.19.0, CPU, statically bundled in published wheel',
        'runtime_version_evidence': 'published package README; adapter also queries native OrtApiBase.GetVersionString',
        'intra_op_threads': 1, 'inter_op_threads': 1,
        'thread_setting_evidence': 'wheel-bundled silero_vad.cpp init_engine_threads(1, 1)',
        'package_license': 'MIT', 'model_license': 'MIT',
        'package_directory': str(packages.resolve()),
    }


class _OrtApiBase(ctypes.Structure):
    # Stable public ONNX Runtime C API struct. No inference is performed here.
    _fields_ = [('GetApi', ctypes.c_void_p),
                ('GetVersionString', ctypes.CFUNCTYPE(ctypes.c_char_p))]


def native_runtime_version(library):
    query = library.OrtGetApiBase
    query.argtypes = []
    query.restype = ctypes.POINTER(_OrtApiBase)
    base = query()
    if not base:
        raise RuntimeError('Bundled ONNX Runtime returned a null OrtApiBase')
    return base.contents.GetVersionString().decode('ascii')


class SileroLiteAdapter:
    sample_rate = 16000
    frame_samples = 512

    def __init__(self, version, install_root=DEFAULT_INSTALL_ROOT):
        global _ACTIVE_INSTALL
        release_spec(version)
        require_supported_platform()
        packages = (Path(install_root) / version / 'packages').resolve()
        identity = (version, str(packages))
        if _ACTIVE_INSTALL is not None and _ACTIVE_INSTALL != identity:
            raise RuntimeError('Silero Lite versions require separate worker processes')
        for name, module in tuple(sys.modules.items()):
            if name == 'silero_vad_lite' or name.startswith('silero_vad_lite.'):
                origin = Path(getattr(module, '__file__', '')).resolve()
                if not origin.is_relative_to(packages):
                    raise RuntimeError('Conflicting silero_vad_lite import; use a fresh worker process')
        self.metadata = verify_installation(version, install_root)
        sys.path.insert(0, str(packages))
        try:
            module = importlib.import_module('silero_vad_lite')
        finally:
            sys.path.pop(0)
        if Path(module.__file__).resolve() != packages / 'silero_vad_lite/__init__.py':
            raise RuntimeError('Silero Lite imported outside the verified version target')
        _ACTIVE_INSTALL = identity
        # No model_path override: benchmark the wheel's actual bundled model.
        self.detector = module.SileroVAD(self.sample_rate)
        if self.detector.sample_rate != self.sample_rate or self.detector.window_size_samples != self.frame_samples:
            raise ValueError('Unexpected Silero Lite native audio contract')
        runtime_version = native_runtime_version(self.detector._lib)
        if runtime_version != '1.19.0':
            raise ValueError(f'Unexpected bundled ONNX Runtime version: {runtime_version}')
        self.metadata.update(
            name=f'silero-lite-{version}', score_kind='probability', score_delay_s=0.0,
            sample_rate=self.sample_rate, frame_samples=self.frame_samples,
            context_samples=64, context_owner='native package; do not prepend context',
            reset_policy='native reset clears recurrent state and audio context',
            inference_path='published package SileroVAD.process(memoryview(float32_frame))',
            isolation='one pinned package target per fresh benchmark worker process',
            native_runtime_version=runtime_version,
            runtime_version_evidence='queried bundled native OrtApiBase.GetVersionString',
        )
        self.reset()

    def reset(self):
        self.detector.reset()

    def process(self, frame):
        frame = np.asarray(frame, dtype=np.float32)
        if frame.shape != (self.frame_samples,):
            raise ValueError('Silero Lite requires mono shape (512,) of fresh samples')
        if not np.all(np.isfinite(frame)) or np.any(np.abs(frame) > 1):
            raise ValueError('Silero Lite requires finite normalized [-1, 1] samples')
        # Writable, native-endian and contiguous is required by ctypes.from_buffer.
        frame = np.require(frame, dtype=np.float32, requirements=['C', 'W', 'A'])
        score = float(self.detector.process(memoryview(frame.data)))
        if not np.isfinite(score) or not 0 <= score <= 1:
            raise ValueError(f'Silero Lite returned invalid probability: {score}')
        return score
