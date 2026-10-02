"""Native smoke tests: skip only absent optional libraries, not broken builds."""
import os
from pathlib import Path
import unittest
import numpy as np
from vadbench.native import ROOT, Agc2Adapter, RNNoiseAdapter, SpeexAdapter, TenAdapter, _pcm16


class NativeTests(unittest.TestCase):
    def test_pcm_boundaries(self):
        self.assertEqual(_pcm16(np.array([-1, 0, 1], np.float32)).tolist(), [-32768, 0, 32767])

    def _exercise(self, cls, name, env):
        if not Path(os.environ.get(env, ROOT / '.deps' / name)).is_file():
            self.skipTest(f'Optional native dependency unavailable: {name}')
        a = cls()
        rng = np.random.default_rng(51)
        frames = [rng.normal(0, 0.08, a.frame_samples).astype(np.float32) for _ in range(20)]
        first = np.array([a.process(x) for x in frames])
        self.assertTrue(np.isfinite(first).all())
        self.assertTrue(((first >= 0) & (first <= 1)).all())
        a.reset()
        second = np.array([a.process(x) for x in frames])
        np.testing.assert_array_equal(first, second)
        for bad in [np.zeros(a.frame_samples+1), np.full(a.frame_samples, np.nan), np.ones(a.frame_samples)*1.1]:
            with self.assertRaises(ValueError):
                a.process(bad)
        self.assertIn('score_delay_s', a.metadata)
        self.assertIn('lookahead_s', a.metadata)
        self.assertEqual(len(a.metadata['library_sha256']), 64)
        a.close()
        a.close()

    def test_rnnoise(self): self._exercise(RNNoiseAdapter, 'librnnoise.so', 'VADBENCH_RNNOISE_LIB')
    def test_speex(self): self._exercise(SpeexAdapter, 'libspeexdsp.so', 'VADBENCH_SPEEX_LIB')
    def test_agc2(self): self._exercise(Agc2Adapter, 'libagc2vad.so', 'VADBENCH_AGC2_LIB')
    def test_ten(self):
        if not os.environ.get('VADBENCH_TEN_LIB'):
            self.skipTest('TEN requires a separately obtained and licensed library')
        self._exercise(TenAdapter, 'libten_vad.so', 'VADBENCH_TEN_LIB')

if __name__ == '__main__':
    unittest.main()
