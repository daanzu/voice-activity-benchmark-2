import unittest
from unittest.mock import patch

import numpy as np

from vadbench.context_ablation import ContextAblationAdapter, MODEL_SHA256


class CapturingSession:
    def __init__(self):
        self.inputs = []

    def run(self, names, feed):
        self.inputs.append({k: v.copy() for k, v in feed.items()})
        return np.array([[.4]], dtype=np.float32), feed['state'] + 1


class ContextContractTests(unittest.TestCase):
    def adapter(self, enabled, sr=16000):
        obj = ContextAblationAdapter.__new__(ContextAblationAdapter)
        obj.context_enabled = enabled
        obj.sample_rate = sr
        obj.frame_samples = sr * 32 // 1000
        obj.context_samples = sr * 4 // 1000
        obj.sr = np.array(sr, dtype=np.int64)
        obj.session = CapturingSession()
        obj.reset()
        return obj

    def test_exact_prefix_contract_and_retained_recurrence_both_rates(self):
        for sr in (8000, 16000):
            for enabled in (False, True):
                with self.subTest(sr=sr, enabled=enabled):
                    a = self.adapter(enabled, sr)
                    frame = np.arange(a.frame_samples, dtype=np.float32)
                    a.process(frame)
                    a.process(frame + 1000)
                    first, second = a.session.inputs
                    prefix = a.context_samples if enabled else 0
                    self.assertEqual(first['input'].shape, (1, a.frame_samples + prefix))
                    np.testing.assert_array_equal(first['input'][0, prefix:], frame)
                    np.testing.assert_array_equal(second['input'][0, prefix:], frame + 1000)
                    if enabled:
                        np.testing.assert_array_equal(first['input'][0, :prefix], 0)
                        np.testing.assert_array_equal(second['input'][0, :prefix], frame[-prefix:])
                    np.testing.assert_array_equal(first['state'], 0)
                    np.testing.assert_array_equal(second['state'], 1)
                    a.reset()
                    a.process(frame)
                    np.testing.assert_array_equal(a.session.inputs[-1]['state'], 0)
                    if enabled:
                        np.testing.assert_array_equal(a.session.inputs[-1]['input'][0, :prefix], 0)

    def test_bad_frame_shape_rejected(self):
        for enabled in (False, True):
            a = self.adapter(enabled)
            for shape in ((511,), (513,), (1, 512)):
                with self.assertRaises(ValueError):
                    a.process(np.zeros(shape))

    def test_real_model_reset_is_exact(self):
        for enabled in (False, True):
            a = ContextAblationAdapter(enabled)
            self.assertEqual(a.metadata['model_sha256'], MODEL_SHA256)
            rng = np.random.default_rng(222)
            frames = [rng.normal(0, .05, a.frame_samples).astype(np.float32) for _ in range(5)]
            first = [a.process(f) for f in frames]
            a.reset()
            self.assertEqual(first, [a.process(f) for f in frames])


if __name__ == '__main__':
    unittest.main()
