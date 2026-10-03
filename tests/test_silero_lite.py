"""Offline unit checks plus fresh-process tests of each optional published wheel."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vadbench import silero_lite as lite


class AudioContractTests(unittest.TestCase):
    def setUp(self):
        self.adapter = lite.SileroLiteAdapter.__new__(lite.SileroLiteAdapter)
        self.adapter.detector = mock.Mock()
        self.adapter.detector.process.return_value = 0.25

    def test_fresh_float32_frame_without_double_context(self):
        frame = np.linspace(-1, 1, 512, dtype=np.float32)
        self.assertEqual(self.adapter.process(frame), 0.25)
        supplied = self.adapter.detector.process.call_args.args[0]
        self.assertIsInstance(supplied, memoryview)
        self.assertEqual(supplied.shape, (512,))
        self.assertEqual(supplied.itemsize, 4)
        self.assertTrue(supplied.contiguous)
        self.assertFalse(supplied.readonly)
        np.testing.assert_array_equal(supplied, frame)
        self.assertTrue(np.shares_memory(np.asarray(supplied), frame))

    def test_read_only_noncontiguous_and_float64_are_normalized_to_buffer_contract(self):
        readonly = np.zeros(512, np.float32)
        readonly.flags.writeable = False
        for frame in (readonly, np.zeros(1024, np.float32)[::2], np.zeros(512, np.float64)):
            self.adapter.process(frame)
            supplied = self.adapter.detector.process.call_args.args[0]
            self.assertEqual(supplied.shape, (512,))
            self.assertEqual(supplied.itemsize, 4)
            self.assertFalse(supplied.readonly)
            self.assertTrue(supplied.contiguous)

    def test_bad_audio_is_rejected_before_native_call(self):
        for frame in (np.zeros(511), np.zeros(576), np.zeros((512, 1)),
                      np.zeros((1, 512)), np.ones(512)*1.01,
                      np.full(512, np.nan), np.full(512, np.inf)):
            with self.subTest(shape=frame.shape), self.assertRaises(ValueError):
                self.adapter.process(frame)
        self.adapter.detector.process.assert_not_called()

    def test_native_reset_and_probability_validation(self):
        self.adapter.reset()
        self.adapter.detector.reset.assert_called_once_with()
        for value in (float('nan'), float('inf'), -.1, 1.1):
            self.adapter.detector.process.return_value = value
            with self.assertRaises(ValueError):
                self.adapter.process(np.zeros(512, np.float32))

    def test_unpinned_version_and_same_process_conflict_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'Unpinned'):
            lite.SileroLiteAdapter('latest')
        with mock.patch.object(lite, 'require_supported_platform'), \
                mock.patch.object(lite, '_ACTIVE_INSTALL', ('0.3.0', '/other')):
            with self.assertRaisesRegex(RuntimeError, 'separate worker processes'):
                lite.SileroLiteAdapter('0.4.0')

    def test_foreign_existing_import_fails_closed(self):
        foreign = types.SimpleNamespace(__file__='/foreign/silero_vad_lite/__init__.py')
        with mock.patch.object(lite, 'require_supported_platform'), \
                mock.patch.object(lite, '_ACTIVE_INSTALL', None), \
                mock.patch.dict(sys.modules, {'silero_vad_lite': foreign}):
            with self.assertRaisesRegex(RuntimeError, 'Conflicting'):
                lite.SileroLiteAdapter('0.3.0')


class IntegrityTests(unittest.TestCase):
    """Tiny synthetic wheels test validation without altering real installations."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / '0.3.0'
        self.packages = self.directory / 'packages'
        self.packages.mkdir(parents=True)

    def fixture(self, metadata_version='0.3.0'):
        files = {
            'silero_vad_lite/__init__.py': b'# wrapper\n',
            'silero_vad_lite/data/silero_vad.onnx': b'pinned model',
            'silero_vad_lite/data/silero_vad_lite.so': b'pinned library',
            'silero_vad_lite-0.3.0.dist-info/METADATA':
                f'Metadata-Version: 2.1\nName: silero-vad-lite\nVersion: {metadata_version}\n'.encode(),
        }
        spec = dict(lite.RELEASES['0.3.0'])
        wheel = self.directory / spec['wheel_filename']
        with zipfile.ZipFile(wheel, 'w') as archive:
            for name, data in files.items():
                archive.writestr(name, data)
                target = self.packages / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        spec['wheel_sha256'] = lite.sha256_file(wheel)
        spec['model_sha256'] = hashlib.sha256(b'pinned model').hexdigest()
        releases = mock.patch.dict(lite.RELEASES, {'0.3.0': spec})
        library = mock.patch.object(lite, 'LIBRARY_SHA256', hashlib.sha256(b'pinned library').hexdigest())
        releases.start(); self.addCleanup(releases.stop)
        library.start(); self.addCleanup(library.stop)
        return wheel

    def test_verified_metadata_and_missing_setup(self):
        with self.assertRaisesRegex(RuntimeError, 'setup_silero_lite'):
            lite.verify_installation('0.3.0', self.root)
        self.fixture()
        metadata = lite.verify_installation('0.3.0', self.root)
        self.assertEqual(metadata['package_version'], '0.3.0')
        self.assertEqual(len(metadata['installed_artifact_sha256']), 4)

    def test_changed_wheel_is_rejected(self):
        wheel = self.fixture()
        with wheel.open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'wheel integrity'):
            lite.verify_installation('0.3.0', self.root)

    def test_changed_model_library_or_wrapper_is_rejected(self):
        self.fixture()
        for relative in ('data/silero_vad.onnx', 'data/silero_vad_lite.so', '__init__.py'):
            path = self.packages / 'silero_vad_lite' / relative
            original = path.read_bytes()
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'installed artifact integrity'):
                lite.verify_installation('0.3.0', self.root)
            path.write_bytes(original)

    def test_wrong_distribution_version_is_rejected(self):
        self.fixture(metadata_version='0.4.0')
        with self.assertRaisesRegex(ValueError, 'distribution version'):
            lite.verify_installation('0.3.0', self.root)


# Every version runs in a fresh interpreter, including the optional ONNX oracle.
# This avoids accidentally measuring a previously imported version/native library.
NATIVE_CHECK = r'''
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np
from vadbench.silero_lite import SileroLiteAdapter
version = sys.argv[1]
adapter = SileroLiteAdapter(version)
assert 'onnxruntime' not in sys.modules and 'torch' not in sys.modules
assert adapter.metadata['package_version'] == version
assert adapter.metadata['context_samples'] == 64
assert adapter.metadata['frame_samples'] == 512
assert adapter.metadata['native_runtime_version'] == '1.19.0'
from silero_vad_lite import SileroVAD
direct = SileroVAD(16000)
rng = np.random.default_rng(93)
frames = rng.uniform(-.12, .12, (24, 512)).astype(np.float32)
frames[0] = 0
frames[3, -64:] = np.linspace(-.8, .8, 64, dtype=np.float32)
actual = [adapter.process(frame) for frame in frames]
expected = [direct.process(memoryview(frame.data)) for frame in frames]
np.testing.assert_array_equal(actual, expected)
for frame in frames[::-1]: adapter.process(frame)
adapter.reset()
assert actual == [adapter.process(frame) for frame in frames]
fresh = SileroLiteAdapter(version)
adapter.reset()
for frame in frames:
    assert adapter.process(frame) == fresh.process(frame)
# Verify the package really owns 64-sample context by comparing native output
# with an independent ONNX invocation of the bundled file in this test only.
oracle_error = None
if importlib.util.find_spec('onnxruntime') is not None:
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    model = Path(adapter.metadata['package_directory']) / 'silero_vad_lite/data/silero_vad.onnx'
    session = ort.InferenceSession(str(model), sess_options=options, providers=['CPUExecutionProvider'])
    state = np.zeros((2, 1, 128), np.float32)
    context = np.zeros((1, 64), np.float32)
    reference = []
    for frame in frames:
        probability, state = session.run(None, {
            'input': np.concatenate([context, frame[None]], axis=1),
            'state': state, 'sr': np.array(16000, dtype=np.int64),
        })
        reference.append(float(probability[0, 0]))
        context = frame[None, -64:].copy()
    np.testing.assert_allclose(actual, reference, atol=3e-6, rtol=1e-5)
    oracle_error = float(np.max(np.abs(np.asarray(actual)-reference)))
try:
    SileroLiteAdapter('0.4.0' if version == '0.3.0' else '0.3.0')
except RuntimeError as exc:
    assert 'separate worker processes' in str(exc)
else:
    raise AssertionError('Cross-version same-process load must fail')
print(json.dumps({'version': version, 'scores': actual, 'oracle_max_absolute_error': oracle_error}))
'''


class NativeWheelTests(unittest.TestCase):
    def run_version(self, version):
        if not (lite.DEFAULT_INSTALL_ROOT / version / 'packages').is_dir():
            self.skipTest('run scripts/setup_silero_lite.py')
        completed = subprocess.run([sys.executable, '-c', NATIVE_CHECK, version],
                                   cwd=ROOT, text=True, capture_output=True, timeout=90)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result['version'], version)
        self.assertEqual(len(result['scores']), 24)

    def test_native_0_3_0(self):
        self.run_version('0.3.0')

    def test_native_0_4_0(self):
        self.run_version('0.4.0')


if __name__ == '__main__':
    unittest.main()
